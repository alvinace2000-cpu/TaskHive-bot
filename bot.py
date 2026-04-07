TaskHive PRO Telegram Bot

Python 3.10+

python-telegram-bot v20

import os import sqlite3 import zipfile from datetime import datetime from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup from telegram.ext import ( Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, )

TOKEN = os.getenv("TOKEN") BOT_USERNAME = "Task_Hive" ADMIN_ID = 8728887265 CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk" MIN_WITHDRAW = 1500

DATA_DIR = "data" FILES_DIR = f"{DATA_DIR}/files"

os.makedirs(DATA_DIR, exist_ok=True) os.makedirs(FILES_DIR, exist_ok=True)

conn = sqlite3.connect(f"{DATA_DIR}/taskhive.db", check_same_thread=False) c = conn.cursor()

USERS

c.execute( """ CREATE TABLE IF NOT EXISTS users( telegram_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, ref_by INTEGER ) """ )

TASKS

c.execute( """ CREATE TABLE IF NOT EXISTS tasks( id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, points INTEGER ) """ )

SUBMISSIONS

c.execute( """ CREATE TABLE IF NOT EXISTS submissions( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER, file TEXT, text TEXT, timestamp TEXT ) """ )

WITHDRAWALS

c.execute( """ CREATE TABLE IF NOT EXISTS withdrawals( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, points INTEGER, method TEXT, status TEXT ) """ )

conn.commit()

pending_task = {}

START

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

user = update.effective_user
user_id = user.id
username = user.username or f"user{user_id}"

ref = None

if context.args:
    arg = context.args[0]
    if arg.startswith("ref_"):
        ref = int(arg.split("_")[1])

c.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
user_data = c.fetchone()

if not user_data:

    c.execute(
        "INSERT INTO users (telegram_id, username, points, ref_by) VALUES (?,?,?,?)",
        (user_id, username, 50, ref),
    )

    conn.commit()

    if ref:
        c.execute("UPDATE users SET points = points + 150 WHERE telegram_id=?", (ref,))
        conn.commit()

    text = f"""

Welcome to TaskHive {username} 🚀

Earn points by completing simple tasks.

Invite friends. Complete surveys. Submit photos and voice tasks.

Join our announcements channel: {CHANNEL_LINK}

You received 50 bonus points.

Use /tasks to start earning. """

else:

    pts = user_data[2]

    text = f"""

Welcome back @{username}

Your current points: {pts}

Use /tasks to continue earning. """

await update.message.reply_text(text)

HELP

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

text = f"""

TaskHive Commands

/start /tasks /profile /referral /withdraw /help

Announcement Channel: {CHANNEL_LINK} """

await update.message.reply_text(text)

PROFILE

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):

uid = update.effective_user.id

c.execute("SELECT points FROM users WHERE telegram_id=?", (uid,))
pts = c.fetchone()[0]

text = f"""

Your Profile

Points: {pts} Minimum Withdraw: {MIN_WITHDRAW} """

await update.message.reply_text(text)

TASKS

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

c.execute("SELECT * FROM tasks")
rows = c.fetchall()

if not rows:
    await update.message.reply_text("No tasks available yet")
    return

kb = []

for t in rows:
    kb.append([InlineKeyboardButton(f"{t[1]} ({t[3]} pts)", callback_data=f"task_{t[0]}")])

await update.message.reply_text("Available Tasks", reply_markup=InlineKeyboardMarkup(kb))

SELECT TASK

async def task_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

q = update.callback_query
await q.answer()

task_id = int(q.data.split("_")[1])

c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
t = c.fetchone()

pending_task[q.from_user.id] = task_id

text = f"""

Task: {t[1]}

{t[2]}

Send your proof now. """

await q.edit_message_text(text)

SUBMISSION

async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):

uid = update.effective_user.id

if uid not in pending_task:
    return

task_id = pending_task.pop(uid)

file_path = None
text = None

if update.message.photo:

    file = await update.message.photo[-1].get_file()

    file_path = f"{FILES_DIR}/{uid}_{datetime.now().timestamp()}.jpg"

    await file.download_to_drive(file_path)

elif update.message.voice:

    file = await update.message.voice.get_file()

    file_path = f"{FILES_DIR}/{uid}_{datetime.now().timestamp()}.ogg"

    await file.download_to_drive(file_path)

else:

    text = update.message.text

c.execute(
    "INSERT INTO submissions (user_id,task_id,file,text,timestamp) VALUES (?,?,?,?,?)",
    (uid, task_id, file_path, text, datetime.now()),
)

c.execute("SELECT points FROM tasks WHERE id=?", (task_id,))

pts = c.fetchone()[0]

c.execute("UPDATE users SET points = points + ? WHERE telegram_id=?", (pts, uid))

conn.commit()

await update.message.reply_text(f"Submission received. +{pts} points")

REFERRAL

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

uid = update.effective_user.id

link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"

await update.message.reply_text(
    f"Your referral link:\n{link}\n\nEarn 150 points per friend"
)

WITHDRAW

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

uid = update.effective_user.id

c.execute("SELECT points FROM users WHERE telegram_id=?", (uid,))

pts = c.fetchone()[0]

if pts < MIN_WITHDRAW:

    await update.message.reply_text(
        f"Minimum withdrawal is {MIN_WITHDRAW} points"
    )

    return

c.execute(
    "INSERT INTO withdrawals (user_id,points,method,status) VALUES (?,?,?,?)",
    (uid, pts, "pending", "pending"),
)

c.execute("UPDATE users SET points = 0 WHERE telegram_id=?", (uid,))

conn.commit()

await update.message.reply_text("Withdrawal request sent to admin")

ADMIN USERS

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

if update.effective_user.id != ADMIN_ID:
    return

c.execute("SELECT username,points FROM users ORDER BY points DESC")

rows = c.fetchall()

text = f"Users: {len(rows)}\n\n"

for r in rows[:50]:
    text += f"@{r[0]} - {r[1]} pts\n"

await update.message.reply_text(text)

ADMIN ADD TASK

async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):

if update.effective_user.id != ADMIN_ID:
    return

try:

    title = context.args[0]
    points = int(context.args[1])

    desc = " ".join(context.args[2:])

    c.execute(
        "INSERT INTO tasks (title,description,points) VALUES (?,?,?)",
        (title, desc, points),
    )

    conn.commit()

    await update.message.reply_text("Task added")

except:

    await update.message.reply_text("Usage: /addtask title points description")

ADMIN ZIP DOWNLOAD

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):

if update.effective_user.id != ADMIN_ID:
    return

zipname = f"{DATA_DIR}/submissions.zip"

with zipfile.ZipFile(zipname, "w") as z:

    for f in os.listdir(FILES_DIR):
        z.write(f"{FILES_DIR}/{f}")

await update.message.reply_document(open(zipname, "rb"))

MAIN

def main():

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("tasks", tasks))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("referral", referral))
app.add_handler(CommandHandler("withdraw", withdraw))

app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("addtask", addtask))
app.add_handler(CommandHandler("export", export))

app.add_handler(CallbackQueryHandler(task_select))

app.add_handler(
    MessageHandler(filters.TEXT | filters.PHOTO | filters.VOICE, submission)
)

print("TaskHive PRO Bot Running...")

app.run_polling()

if name == "main": main()
