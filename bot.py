import sqlite3
import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TOKEN = os.getenv("TOKEN")
BOT_USERNAME = "TaskHiveDataBot"

MIN_WITHDRAW = 1500
NEW_USER_BONUS = 50
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

# Google Drive setup
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS_JSON")
DRIVE_FOLDER_NAME = "TaskHive-Data"

if GOOGLE_CREDENTIALS:
    creds_info = json.loads(GOOGLE_CREDENTIALS)
    credentials = Credentials.from_service_account_info(creds_info, scopes=['https://www.googleapis.com/auth/drive'])
    drive_service = build('drive', 'v3', credentials=credentials)
else:
    drive_service = None

# Local folders (backup)
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

async def upload_to_drive(file_path, file_name):
    if not drive_service:
        return "No Google Drive connected"
    try:
        file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_NAME]}
        media = MediaFileUpload(file_path, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return f"https://drive.google.com/file/d/{file.get('id')}/view"
    except Exception as e:
        return f"Upload failed: {e}"

# Rest of the code (start, tasks, etc.) is the same as last version but with drive upload

# ... (I’ll send the full code in the next message because it's long)

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
    print("🚀 TaskHive is LIVE with Google Drive backup!")
    app.run_polling()

if __name__ == "__main__":
    main()
