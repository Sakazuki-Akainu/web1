import os
import json
import requests
from flask import Flask, request, redirect, url_for, session, render_template
# --- THIS IS THE FIX ---
# We are adding the password functions back in.
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# --- SETUP ---
USERS_FILE = 'users.json'
UPLOADS_DIR = 'static/uploads'
os.makedirs(UPLOADS_DIR, exist_ok=True)


# --- DATABASE FUNCTIONS ---
def load_users():
    if not os.path.exists(USERS_FILE): return {}
    with open(USERS_FILE, 'r') as f: return json.load(f)

def save_users(users_data):
    with open(USERS_FILE, 'w') as f: json.dump(users_data, f, indent=4)


# --- TELEGRAM SETUP ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_country_from_ip(ip):
    if ip == '127.0.0.1': return "Local"
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=country")
        return response.json().get('country', 'Unknown') if response.status_code == 200 else "Unknown"
    except Exception: return "Unknown"

def send_to_telegram(message, username_to_approve=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    if username_to_approve:
        keyboard = {"inline_keyboard": [[
            {"text": "✅ Allow", "callback_data": f"allow:{username_to_approve}"},
            {"text": "❌ Deny", "callback_data": f"deny:{username_to_approve}"}
        ]]}
        payload['reply_markup'] = keyboard
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(api_url, json=payload)
    except Exception as e: print(f"Failed to send message: {e}")


# --- TELEGRAM WEBHOOK ---
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
            reply_text = f"🤔 User '{username}' not found."

        edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
        requests.post(edit_url, json={'chat_id': chat_id, 'message_id': message_id, 'text': reply_text})

    elif "message" in update and "photo" in update["message"]:
        message = update["message"]
        chat_id = message["chat"]["id"]
        
        if str(chat_id) != TELEGRAM_CHAT_ID:
            send_to_telegram("Sorry, only the admin can upload photos.", chat_id)
            return "ok", 200

        file_id = message["photo"][-1]["file_id"]
        get_file_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        res = requests.get(get_file_url)
        file_path = res.json()["result"]["file_path"]
        
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        image_data = requests.get(download_url).content
        
        image_filename = os.path.basename(file_path)
        save_path = os.path.join(UPLOADS_DIR, image_filename)
        with open(save_path, "wb") as f:
            f.write(image_data)
        
        send_to_telegram(f"🖼️ Image '{image_filename}' uploaded successfully!")

    return "ok", 200


# --- REGULAR ROUTES ---

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
        send_to_telegram(log_message, username_to_approve=username)

        return redirect(url_for('unauthorized'))
    return render_template("signup.html")

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

@app.route('/gallery')
def gallery():
    users = load_users()
    if 'username' in session and users.get(session['username'], {}).get('allowed'):
        image_files = [f for f in os.listdir(UPLOADS_DIR) if os.path.isfile(os.path.join(UPLOADS_DIR, f))]
        return render_template("gallery.html", username=session['username'], images=image_files)
    
    return redirect(url_for('home'))

@app.route('/unauthorized')
def unauthorized():
    return render_template("unauthorized.html")

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))
