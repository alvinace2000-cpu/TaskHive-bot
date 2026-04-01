import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

TOKEN = "8521312991:AAG6ELlY_hvF3aKiCN259CBDgCK5wL35AY4"
BOT_USERNAME = "TaskHiveDataBot"

MIN_WITHDRAW = 1500
REFERRAL_BONUS = 150
NEW_USER_BONUS = 50

conn = sqlite3.connect("taskhive.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_type TEXT, timestamp TEXT)''')
conn.commit()

if not os.path.exists("submissions"):
    os.makedirs("submissions")

TASKS = {
    "1": {"name": "📷 Local Photo", "points": 40, "desc": "Take one clear photo of your surroundings (street, market, shop, food, etc.). Make sure it is not blurry."},
    "2": {"name": "🎙️ Voice Description", "points": 80, "desc": "Record a 10-15 second voice note describing what you see right now (people, buildings, weather, market, etc.). Speak naturally."},
    "3": {"name": "📝 Local Prices Survey", "points": 50, "desc": "Tell us current prices: 1kg rice, 1kg sugar, loaf of bread, plate of ugali + meat."},
    "4": {"name": "🍲 Popular Local Food", "points": 40, "desc": "What is the most popular food or drink in your area and why?"},
    "5": {"name": "🔄 English to Swahili Translation", "points": 70, "desc": "Translate 5 simple English sentences to natural Swahili."}
}

user_pending = {}

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
    await query.edit_message_text(f"✅ Task started:\n{task['name']}\n\n{task['desc']}\n\nSend your photo, voice or text now.")

async def handle_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_pending: return
    task_id = user_pending.pop(user_id)
    task = TASKS[task_id]
    c.execute("INSERT INTO submissions (user_id, task_type, timestamp) VALUES (?, ?, ?)", (user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id = ?", (task["points"], user_id))
    conn.commit()
    await update.message.reply_text(f"✅ Task completed!\nYou earned +{task['points']} points!")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT points FROM users WHERE telegram_id = ?", (user_id,))
    pts = c.fetchone()[0] if c.fetchone() else 0
    status = "✅ Ready to withdraw" if pts >= MIN_WITHDRAW else f"Need {MIN_WITHDRAW - pts} more points"
    await update.message.reply_text(f"💰 Your points: **{pts}**\n{status}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, handle_submission))
    print("🚀 TaskHive is LIVE!")
    app.run_polling()

if __name__ == "__main__":
    main()
