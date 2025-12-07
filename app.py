import os
import requests
from flask import Flask, request, redirect, url_for, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'a_default_secret_key_for_local_dev')

# --- USER DATABASE ---
# This is still an in-memory dictionary. New users will be added here.
# For now, you approve users by changing 'allowed' to True and restarting the app.
users = {
    "franky": {
        "password": generate_password_hash("artlover123"),
        "allowed": True
    }
}

# --- TELEGRAM SETUP ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_country_from_ip(ip):
    """Gets country information from an IP address using a free API."""
    if ip == '127.0.0.1': # This is a local IP, API won't work
        return "Local"
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=country")
        if response.status_code == 200:
            return response.json().get('country', 'Unknown')
    except Exception:
        return "Unknown"
    return "Unknown"

def send_to_telegram(message):
    """Sends a message to your Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram environment variables not set.")
        return
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(api_url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
    except Exception as e:
        print(f"Failed to send message to Telegram: {e}")

# --- ROUTES ---

@app.route("/")
def home():
    if 'username' in session:
        return redirect(url_for('gallery'))
    return render_template("index.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        country = get_country_from_ip(user_ip)

        if username in users:
            return render_template("signup.html", error="Username already exists. Please choose another.")

        # Add the new user, but mark them as not allowed
        users[username] = {
            "password": generate_password_hash(password),
            "allowed": False
        }

        # Notify yourself that a new user signed up
        log_message = (f"👋 New Signup: User '{username}' from {country} (IP: {user_ip}) "
                       f"is waiting for approval.")
        send_to_telegram(log_message)

        return redirect(url_for('unauthorized'))

    return render_template("signup.html")


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    country = get_country_from_ip(user_ip)

    user = users.get(username)

    if user and check_password_hash(user['password'], password):
        if user['allowed']:
            session['username'] = username
            log_message = f"✅ Access Granted: User '{username}' from {country} (IP: {user_ip}) logged in."
            send_to_telegram(log_message)
            return redirect(url_for('gallery'))
        else:
            log_message = (f"🔒 Pending Approval: User '{username}' from {country} (IP: {user_ip}) "
                           f"tried to log in.")
            send_to_telegram(log_message)
            return redirect(url_for('unauthorized'))

    log_message = f"❌ Failed Login: Attempt for user '{username}' from {country} (IP: {user_ip})."
    send_to_telegram(log_message)
    return render_template("index.html", error="Invalid username or password.")


@app.route('/gallery')
def gallery():
    if 'username' in session and users.get(session['username'], {}).get('allowed'):
        return render_template("gallery.html", username=session['username'])
    return redirect(url_for('home'))

@app.route('/unauthorized')
def unauthorized():
    return render_template("unauthorized.html")

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
