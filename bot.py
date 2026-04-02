import sqlite3
import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("TOKEN")
BOT_USERNAME = "TaskHiveDataBot"

MIN_WITHDRAW = 1500
REFERRAL_BONUS = 150
NEW_USER_BONUS = 50

# Fixed path for Render.com
DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "taskhive.db")
SUBMISSIONS_DIR = os.path.join(DATA_DIR, "submissions")
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_type TEXT, timestamp TEXT, file_path TEXT)''')
conn.commit()

TASKS = {
    "1": {"name": "📷 Local Photo", "points": 40, "desc": "Take one clear photo of your surroundings."},
    "2": {"name": "🎙️ Voice Description", "points": 80, "desc": "Record 10-15 second voice note describing what you see."},
    "3": {"name": "📝 Local Prices Survey", "points": 50, "desc": "Tell us current prices of basic items."},
    "4": {"name": "🍲 Popular Local Food", "points": 40, "desc": "What is the most popular food/drink in your area?"},
    "5": {"name": "🔄 English to Swahili Translation", "points": 70, "desc": "Translate 5 simple English sentences."}
}

user_pending = {}

# ... (rest of the functions remain the same - start, tasks, button_handler, handle_submission, points, referral, help_command)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username, points) VALUES (?, ?, ?)", (user_id, username, NEW_USER_BONUS))
    conn.commit()
    await update.message.reply_text(f"👋 Welcome to TaskHive!\nYou got {NEW_USER_BONUS} bonus points!\n\nUse /tasks to start earning.")

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(f"{task['name']} — {task['points']} pts", callback_data=key)] for key, task in TASKS.items()]
    await update.message.reply_text("📋 Available Tasks", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = query.data
    task = TASKS[task_id]
    user_pending[query.from_user.id] = task_id
    await query.edit_message_text(f"✅ Task: {task['name']}\n\n{task['desc']}\n\nSend your response now.")

async def handle_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_pending: return
    task_id = user_pending.pop(user_id)
    task = TASKS[task_id]

    file_path = None
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = os.path.join(SUBMISSIONS_DIR, f"{user_id}_photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        await file.download_to_drive(file_path)
    elif update.message.voice:
        voice = update.message.voice
        file = await voice.get_file()
        file_path = os.path.join(SUBMISSIONS_DIR, f"{user_id}_voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg")
        await file.download_to_drive(file_path)

    c.execute("INSERT INTO submissions (user_id, task_type, timestamp, file_path) VALUES (?, ?, ?, ?)",
              (user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M"), file_path))
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id = ?", (task["points"], user_id))
    conn.commit()

    await update.message.reply_text(f"✅ Task completed!\nYou earned +{task['points']} points!")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT points FROM users WHERE telegram_id = ?", (user_id,))
    result = c.fetchone()
    pts = result[0] if result else 0
    status = "✅ Ready to withdraw" if pts >= MIN_WITHDRAW else f"Need {MIN_WITHDRAW - pts} more points"
    await update.message.reply_text(f"💰 Your points: **{pts}**\n{status}")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"🔗 Your referral link:\nhttps://t.me/{BOT_USERNAME}?start=ref_{user_id}\n\nShare and earn {REFERRAL_BONUS} points per friend!")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, handle_submission))
    print("🚀 TaskHive is LIVE on Render!")
    app.run_polling()

if __name__ == "__main__":
    main()
