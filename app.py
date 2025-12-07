import os
import requests
from flask import Flask, request, redirect, url_for, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Render will need this secret key to be set as an environment variable
app.secret_key = os.environ.get('SECRET_KEY', 'a_default_secret_key_for_local_dev')

# --- USER DATABASE ---
# WARNING: This is a simple in-memory dictionary.
# For a real-world application, you would use a proper database.
# The password for 'franky' is 'artlover123'
users = {
    "franky": {
        "password": generate_password_hash("artlover123"),
        "allowed": True  # This user is pre-approved
    },
    "new_user": {
        "password": generate_password_hash("password"),
        "allowed": False # This user is NOT yet approved
    }
}

# --- TELEGRAM SETUP ---
# Get these from your environment variables on Render
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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
    # If the user is already logged in, send them to the gallery
    if 'username' in session:
        return redirect(url_for('gallery'))
    # Otherwise, show the login page
    return render_template("index.html")

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    user = users.get(username)

    # Check if user exists and password is correct
    if user and check_password_hash(user['password'], password):
        if user['allowed']:
            session['username'] = username
            log_message = f"✅ Access Granted: User '{username}' logged in from IP: {user_ip}"
            send_to_telegram(log_message)
            return redirect(url_for('gallery'))
        else:
            # User exists but is not yet allowed
            log_message = f"🔒 Pending Approval: User '{username}' tried to log in from IP: {user_ip}"
            send_to_telegram(log_message)
            return redirect(url_for('unauthorized'))

    # If login fails
    log_message = f"❌ Failed Login: Attempt for user '{username}' from IP: {user_ip}"
    send_to_telegram(log_message)
    return render_template("index.html", error="Invalid username or password.")


@app.route('/gallery')
def gallery():
    # Protect this page
    if 'username' in session and users.get(session['username'], {}).get('allowed'):
        return render_template("gallery.html", username=session['username'])
    # If not logged in or not allowed, redirect to login
    return redirect(url_for('home'))

@app.route('/unauthorized')
def unauthorized():
    return render_template("unauthorized.html")


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    # This part is for local testing only. Render uses Gunicorn.
    app.run(debug=True)
