import os
import json
import requests
from flask import Flask, request, redirect, url_for, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# --- USER DATABASE (NOW A JSON FILE) ---
USERS_FILE = 'users.json'

def load_users():
    """Loads the users from the JSON file."""
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users_data):
    """Saves the users to the JSON file."""
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f, indent=4)

# --- TELEGRAM SETUP ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_country_from_ip(ip):
    if ip == '127.0.0.1': return "Local"
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=country")
        return response.json().get('country', 'Unknown') if response.status_code == 200 else "Unknown"
    except Exception:
        return "Unknown"

# MODIFIED: Now sends messages with buttons
def send_to_telegram(message, username_to_approve=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram environment variables not set.")
        return

    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}

    # If a username is provided, add Allow/Deny buttons
    if username_to_approve:
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Allow", "callback_data": f"allow:{username_to_approve}"},
                {"text": "❌ Deny", "callback_data": f"deny:{username_to_approve}"}
            ]]
        }
        payload['reply_markup'] = keyboard

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(api_url, json=payload)
    except Exception as e:
        print(f"Failed to send message to Telegram: {e}")

# --- ROUTES ---

@app.route("/")
def home():
    if 'username' in session: return redirect(url_for('gallery'))
    return render_template("index.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users = load_users()
        if username in users:
            return render_template("signup.html", error="Username already exists.")

        users[username] = {"password": generate_password_hash(password), "allowed": False}
        save_users(users)
        
        user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        country = get_country_from_ip(user_ip)
        
        log_message = f"👋 New Signup: User '{username}' from {country} is waiting for approval."
        # Send the notification with the new user's name for the buttons
        send_to_telegram(log_message, username_to_approve=username)

        return redirect(url_for('unauthorized'))
    return render_template("signup.html")

# Login route is now simpler, just loads users
@app.route('/login', methods=['POST'])
def login():
    users = load_users()
    username = request.form['username']
    password = request.form['password']
    user = users.get(username)

    if user and check_password_hash(user['password'], password):
        if user['allowed']:
            session['username'] = username
            return redirect(url_for('gallery'))
        else:
            return redirect(url_for('unauthorized'))

    return render_template("index.html", error="Invalid username or password.")


# --- NEW: THE TELEGRAM WEBHOOK ---
@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if "callback_query" in update:
        data = update["callback_query"]["data"]
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        message_id = update["callback_query"]["message"]["message_id"]

        action, username = data.split(":")
        
        users = load_users()
        
        if username in users:
            if action == "allow":
                users[username]["allowed"] = True
                save_users(users)
                reply_text = f"✅ User '{username}' has been approved."
            elif action == "deny":
                del users[username]
                save_users(users)
                reply_text = f"❌ User '{username}' has been denied and removed."
        else:
            reply_text = f"🤔 User '{username}' not found. They may have been actioned already."

        # Edit the original message to remove the buttons and show the result
        edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
        requests.post(edit_url, json={'chat_id': chat_id, 'message_id': message_id, 'text': reply_text})

    return "ok", 200

# Other routes remain the same
@app.route('/gallery')
def gallery():
    users = load_users()
    if 'username' in session and users.get(session['username'], {}).get('allowed'):
        return render_template("gallery.html", username=session['username'])
    return redirect(url_for('home'))

@app.route('/unauthorized')
def unauthorized(): return render_template("unauthorized.html")

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))
