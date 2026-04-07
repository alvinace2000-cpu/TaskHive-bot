TaskHive Telegram Bot (Advanced)

Features: tasks, referrals, withdrawals, admin panel, submissions

import os import sqlite3 import zipfile from datetime import datetime from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import ( ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler )

TOKEN = os.getenv("TOKEN") ADMIN_ID = 8728887265 CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk" MIN_WITHDRAW = 1500

conn = sqlite3.connect("taskhive.db", check_same_thread=False) c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users ( user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0 )""")

c.execute("""CREATE TABLE IF NOT EXISTS tasks ( id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, points INTEGER )""")

c.execute("""CREATE TABLE IF NOT EXISTS submissions ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER, text TEXT, file_path TEXT )""")

c.execute("""CREATE TABLE IF NOT EXISTS withdrawals ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, wallet TEXT, points INTEGER, status TEXT )""")

conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user

c.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
exists = c.fetchone()

if not exists:
    c.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username))
    conn.commit()

    await update.message.reply_text(
        f"""👋 Welcome to TaskHive

Earn points by completing simple online tasks.

📢 Join announcements: {CHANNEL_LINK}

Use /tasks to start earning.""" )

else:
    c.execute("SELECT points FROM users WHERE user_id=?", (user.id,))
    points = c.fetchone()[0]

    await update.message.reply_text(
        f"Welcome back @{user.username}\n\n⭐ Points: {points}\n\nUse /tasks to earn more."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text( f"""Commands:

/tasks - View tasks /profile - Your stats /referral - Get referral link /withdraw - Withdraw points

📢 Channel: {CHANNEL_LINK}""" )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user

c.execute("SELECT points, referrals FROM users WHERE user_id=?", (user.id,))
data = c.fetchone()

await update.message.reply_text(
    f"👤 @{user.username}\n⭐ Points: {data[0]}\n👥 Referrals: {data[1]}"
)

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE): c.execute("SELECT * FROM tasks") tasks = c.fetchall()

if not tasks:
    await update.message.reply_text("No tasks available right now.")
    return

for task in tasks:
    keyboard = [[InlineKeyboardButton("Submit", callback_data=f"task_{task[0]}")]]

    await update.message.reply_text(
        f"📌 {task[1]}\n{task[2]}\n⭐ Reward: {task[3]} pts",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE): query = update.callback_query await query.answer()

task_id = query.data.split("_")[1]

context.user_data["task"] = task_id

await query.message.reply_text("Send your proof (text or screenshot).")

async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE): if "task" not in context.user_data: return

task_id = context.user_data["task"]
user = update.effective_user

text = update.message.text if update.message.text else ""
file_path = None

if update.message.photo:
    photo = update.message.photo[-1]
    file = await photo.get_file()
    path = f"sub_{user.id}_{datetime.now().timestamp()}.jpg"
    await file.download_to_drive(path)
    file_path = path

c.execute(
    "INSERT INTO submissions (user_id, task_id, text, file_path) VALUES (?, ?, ?, ?)",
    (user.id, task_id, text, file_path)
)

conn.commit()

await update.message.reply_text("✅ Submission received.")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user

link = f"https://t.me/{context.bot.username}?start={user.id}"

await update.message.reply_text(f"Your referral link:\n{link}")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE): user = update.effective_user

c.execute("SELECT points FROM users WHERE user_id=?", (user.id,))
points = c.fetchone()[0]

if points < MIN_WITHDRAW:
    await update.message.reply_text(
        f"Minimum withdrawal is {MIN_WITHDRAW} points."
    )
    return

context.user_data["withdraw"] = True

await update.message.reply_text("Send your wallet or payment address.")

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE): if "withdraw" not in context.user_data: return

user = update.effective_user
wallet = update.message.text

c.execute("SELECT points FROM users WHERE user_id=?", (user.id,))
points = c.fetchone()[0]

c.execute(
    "INSERT INTO withdrawals (user_id, wallet, points, status) VALUES (?, ?, ?, 'pending')",
    (user.id, wallet, points)
)

c.execute("UPDATE users SET points=0 WHERE user_id=?", (user.id,))

conn.commit()

await update.message.reply_text("💰 Withdrawal request submitted.")

async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE): if update.effective_user.id != ADMIN_ID: return

title = context.args[0]
points = int(context.args[1])
description = " ".join(context.args[2:])

c.execute(
    "INSERT INTO tasks (title, description, points) VALUES (?, ?, ?)",
    (title, description, points)
)

conn.commit()

await update.message.reply_text("Task added.")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE): if update.effective_user.id != ADMIN_ID: return

c.execute("SELECT COUNT(*) FROM users")
total = c.fetchone()[0]

await update.message.reply_text(f"Total users: {total}")

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE): if update.effective_user.id != ADMIN_ID: return

c.execute("SELECT file_path FROM submissions WHERE file_path IS NOT NULL")
files = c.fetchall()

zip_name = "submissions.zip"

with zipfile.ZipFile(zip_name, "w") as z:
    for f in files:
        if os.path.exists(f[0]):
            z.write(f[0])

await update.message.reply_document(open(zip_name, "rb"))

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start)) app.add_handler(CommandHandler("help", help_command)) app.add_handler(CommandHandler("tasks", tasks)) app.add_handler(CommandHandler("profile", profile)) app.add_handler(CommandHandler("referral", referral)) app.add_handler(CommandHandler("withdraw", withdraw)) app.add_handler(CommandHandler("addtask", addtask)) app.add_handler(CommandHandler("users", users)) app.add_handler(CommandHandler("download_submissions", download))

app.add_handler(CallbackQueryHandler(button))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wallet)) app.add_handler(MessageHandler(filters.ALL, submission))

print("TaskHive Bot Running...") app.run_polling()
