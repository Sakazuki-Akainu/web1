import os
import json
import requests
from flask import Flask, request, redirect, url_for, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

# --- SETUP ---
USERS_FILE = 'users.json'
BOT_STATE_FILE = 'bot_state.json'
UPLOADS_DIR = 'static/uploads'
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOADS_DIR, 'Default'), exist_ok=True)

# --- HELPER FUNCTIONS ---
def load_json(filename):
    if not os.path.exists(filename): return {}
    with open(filename, 'r') as f: return json.load(f)

def save_json(data, filename):
    with open(filename, 'w') as f: json.dump(data, f, indent=4)

def send_telegram_message(text, chat_id=None):
    if not chat_id: chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not chat_id: return
    payload = {'chat_id': chat_id, 'text': text}
    api_url = f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/sendMessage"
    try: requests.post(api_url, json=payload)
    except Exception as e: print(f"Failed to send message: {e}")

# --- THE TELEGRAM WEBHOOK ---
@app.route(f"/webhook/{os.environ.get('TELEGRAM_BOT_TOKEN')}", methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if not update: return "ok", 200

    # Only handle messages from now on, callbacks are separate
    if "message" in update:
        message = update["message"]
        chat_id = str(message["chat"]["id"])

        # SECURITY: Only you can perform actions
        if chat_id != os.environ.get("TELEGRAM_CHAT_ID"): return "ok", 200

        # --- Part 1: Handle Text Commands ---
        if "text" in message:
            text = message["text"]
            state = load_json(BOT_STATE_FILE)

            if text.startswith('/start_batch '):
                chapter_name = text.split(' ', 1)[1].strip()
                if chapter_name:
                    # Create the chapter folder if it doesn't exist
                    os.makedirs(os.path.join(UPLOADS_DIR, chapter_name), exist_ok=True)
                    # Update the bot's state
                    state['batch_mode'] = True
                    state['batch_chapter'] = chapter_name
                    save_json(state, BOT_STATE_FILE)
                    send_telegram_message(f"✅ Batch mode STARTED. All new photos will be added to chapter '{chapter_name}'.")
                else:
                    send_telegram_message("⚠️ Please provide a chapter name. Usage: /start_batch <Chapter Name>")

            elif text == '/end_batch':
                if state.get('batch_mode'):
                    state['batch_mode'] = False
                    state['batch_chapter'] = None
                    save_json(state, BOT_STATE_FILE)
                    send_telegram_message("🛑 Batch mode ENDED.")
                else:
                    send_telegram_message("ℹ️ Batch mode is not currently active.")
            
            # You can keep other commands like /current_chapter if you want
            elif text == '/current_batch':
                if state.get('batch_mode'):
                    send_telegram_message(f"📖 Batch mode is ON for chapter '{state.get('batch_chapter')}'.")
                else:
                    send_telegram_message("ℹ️ Batch mode is OFF.")


        # --- Part 2: Handle Photos (Checks for Batch Mode) ---
        elif "photo" in message:
            state = load_json(BOT_STATE_FILE)

            # Only process photo if batch mode is active
            if state.get('batch_mode') == True:
                chapter_name = state.get('batch_chapter')
                if not chapter_name:
                    send_telegram_message("Error: Batch mode is on but no chapter is set. Please use /end_batch and start again.")
                    return "ok", 200
                
                # Download photo logic (unchanged)
                file_id = message["photo"][-1]["file_id"]
                get_file_url = f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/getFile?file_id={file_id}"
                res = requests.get(get_file_url).json()
                file_path = res["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{os.environ.get('TELEGRAM_BOT_TOKEN')}/{file_path}"
                image_data = requests.get(download_url).content
                
                # Save photo to the correct batch chapter folder
                image_filename = os.path.basename(file_path)
                save_path = os.path.join(UPLOADS_DIR, chapter_name, image_filename)
                with open(save_path, "wb") as f:
                    f.write(image_data)
                
                # We don't need to send a confirmation for every single photo in a batch
                # It keeps the chat cleaner. You'll know it's working.
            else:
                send_telegram_message("ℹ️ Photo received, but batch mode is off. Use `/start_batch <Chapter Name>` to begin uploading.")

    # User approval logic can be added back here if needed, but this focuses on the batch upload feature
    return "ok", 200

# --- ALL WEBSITE ROUTES ---
# No changes are needed for any of your website routes (@app.route(...))
# They will all work perfectly with the new folder structure.
# I am omitting them here for brevity, but you should KEEP your existing routes
# for /gallery, /view_chapter, /login, /signup, etc.
@app.route("/")
def home():
    if 'username' in session: return redirect(url_for('gallery'))
    return render_template("index.html")

@app.route('/gallery')
def gallery():
    users = load_json(USERS_FILE)
    if 'username' in session and users.get(session.get('username'), {}).get('allowed'):
        chapters = [d for d in os.listdir(UPLOADS_DIR) if os.path.isdir(os.path.join(UPLOADS_DIR, d))]
        return render_template("gallery.html", username=session['username'], chapters=chapters)
    return redirect(url_for('home'))

@app.route('/gallery/<chapter_name>')
def view_chapter(chapter_name):
    users = load_json(USERS_FILE)
    if 'username' in session and users.get(session.get('username'), {}).get('allowed'):
        chapter_path = os.path.join(UPLOADS_DIR, chapter_name)
        if not os.path.isdir(chapter_path): return "Chapter not found", 404
        images = [f for f in os.listdir(chapter_path) if f != '.gitkeep']
        return render_template("chapter.html", username=session['username'], chapter_name=chapter_name, images=images)
    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    users = load_json(USERS_FILE)
    username = request.form['username']
    password = request.form['password']
    user = users.get(username)
    if user and check_password_hash(user['password'], password):
        if user.get('allowed'):
            session['username'] = username
            return redirect(url_for('gallery'))
        else:
            return redirect(url_for('unauthorized'))
    return render_template("index.html", error="Invalid username or password.")

# ... and so on for signup, logout, unauthorized.
