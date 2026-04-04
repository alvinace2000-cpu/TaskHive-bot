import sqlite3
import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import dropbox
from dropbox.exceptions import AuthError

TOKEN = os.getenv("TOKEN")
BOT_USERNAME = "TaskHiveDataBot"
ADMIN_ID = 8728887265

MIN_WITHDRAW = 1500
NEW_USER_BONUS = 50
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

# Dropbox Setup
DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")
DROPBOX_FOLDER = "/TaskHive-Data"   # Change if your folder name is different

dbx = None
if DROPBOX_TOKEN:
    try:
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        print("✅ Dropbox connected successfully!")
    except Exception as e:
        print(f"⚠️ Dropbox connection failed: {e}")

# Local backup
DATA_DIR = "data"
SUBMISSIONS_DIR = os.path.join(DATA_DIR, "submissions")
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)

conn = sqlite3.connect(os.path.join(DATA_DIR, "taskhive.db"), check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_type TEXT, timestamp TEXT, file_path TEXT)''')
conn.commit()

TASKS = {
    "1": {"name": "📷 Local Photo", "points": 40, "desc": "Take one clear photo of your surroundings."},
    "2": {"name": "🎙️ Voice Description", "points": 80, "desc": "Record 10-15 second voice note describing what you see."},
    "3": {"name": "📝 Local Prices Survey", "points": 50, "desc": "Tell us current prices: 1kg rice, 1kg sugar, loaf of bread, plate of ugali + meat."},
    "4": {"name": "🍲 Popular Local Food", "points": 40, "desc": "What is the most popular food/drink in your area?"},
    "5": {"name": "🔄 English to Swahili Translation", "points": 70, "desc": "Translate 5 simple English sentences."}
}

user_pending = {}

async def upload_to_dropbox(file_path, file_name):
    if not dbx:
        return None
    try:
        dropbox_path = f"{DROPBOX_FOLDER}/{file_name}"
        with open(file_path, "rb") as f:
            dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
        print(f"✅ Uploaded to Dropbox: {file_name}")
        return f"https://www.dropbox.com/home{ DROPBOX_FOLDER }/{file_name}"
    except Exception as e:
        print(f"⚠️ Dropbox upload error: {e}")
        return None

# Rest of the bot (start, tasks, etc.)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"

    c.execute("SELECT points FROM users WHERE telegram_id = ?", (user_id,))
    result = c.fetchone()

    if result:
        pts = result[0]
        await update.message.reply_text(f"👋 Welcome back, @{username}!\nYou currently have **{pts} points**.\n\nUse /tasks to continue earning.")
    else:
        c.execute("INSERT INTO users (telegram_id, username, points) VALUES (?, ?, ?)", (user_id, username, NEW_USER_BONUS))
        conn.commit()
        await update.message.reply_text(
            f"👋 Welcome to TaskHive, @{username}!\n\n"
            f"You received **{NEW_USER_BONUS} bonus points**!\n\n"
            f"Join our Announcement Channel:\n{CHANNEL_LINK}\n\n"
            f"Use /tasks to start earning."
        )

# (The rest of the functions are the same as before - tasks, button_handler, handle_submission, points, referral, help_command, admin)

async def handle_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_pending:
        return
    task_id = user_pending.pop(user_id)
    task = TASKS[task_id]

    file_path = None
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_path = os.path.join(SUBMISSIONS_DIR, f"{user_id}_photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        await file.download_to_drive(file_path)
    elif update.message.voice:
        file = await update.message.voice.get_file()
        file_path = os.path.join(SUBMISSIONS_DIR, f"{user_id}_voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg")
        await file.download_to_drive(file_path)

    # Upload to Dropbox
    dropbox_link = await upload_to_dropbox(file_path, os.path.basename(file_path)) if file_path else None

    c.execute("INSERT INTO submissions (user_id, task_type, timestamp, file_path) VALUES (?, ?, ?, ?)",
              (user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M"), file_path))
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id = ?", (task["points"], user_id))
    conn.commit()

    msg = f"✅ Task completed!\nYou earned +{task['points']} points!"
    if dropbox_link:
        msg += "\n📁 Saved to Dropbox"
    await update.message.reply_text(msg)

# Add the rest of the functions (points, referral, help_command, admin) as before...

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, handle_submission))
    print("🚀 TaskHive is LIVE with Dropbox backup!")
    app.run_polling()

if __name__ == "__main__":
    main()
