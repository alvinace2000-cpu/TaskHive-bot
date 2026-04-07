import os
import sqlite3
import zipfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
CallbackQueryHandler,
ContextTypes,
filters
)

TOKEN = os.getenv("TOKEN")

BOT_USERNAME = "Task_Hive"
ADMIN_ID = 8728887265
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
SUB_DIR = f"{DATA_DIR}/submissions"

os.makedirs(SUB_DIR, exist_ok=True)

conn = sqlite3.connect(f"{DATA_DIR}/taskhive.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0,
ref_by INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS tasks(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
description TEXT,
points INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS submissions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
task_id INTEGER,
file_path TEXT,
text_answer TEXT,
time TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
amount INTEGER,
wallet TEXT,
status TEXT
)""")

conn.commit()

pending_task = {}
pending_withdraw = {}

MIN_WITHDRAW = 1500


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or "user"

    ref = None
    if context.args:
        if "ref_" in context.args[0]:
            ref = int(context.args[0].split("_")[1])

    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    result = c.fetchone()

    if result:

        pts = result[2]

        await update.message.reply_text(
f"""👋 Welcome back @{username}

💰 Your Points: {pts}

Use /tasks to start earning more points."""
)

    else:

        c.execute(
"INSERT INTO users(id,username,points,ref_by) VALUES(?,?,?,?)",
(user_id, username, 50, ref)
)

        conn.commit()

        if ref and ref != user_id:

            c.execute(
"UPDATE users SET points = points + 150 WHERE id=?",
(ref,)
)

            conn.commit()

        await update.message.reply_text(
f"""👋 Welcome to TaskHive @{username}

You received 🎁 50 bonus points!

Complete tasks and earn rewards.

Join announcements👇
{CHANNEL_LINK}

Use /tasks to start."""
)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
f"""
🛠 TaskHive Commands

/start
/tasks
/profile
/referral
/withdraw

Join announcements👇
{CHANNEL_LINK}
"""
)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (user_id,))
    pts = c.fetchone()[0]

    await update.message.reply_text(
f"""
👤 Profile

💰 Points: {pts}

Minimum withdrawal: {MIN_WITHDRAW}
"""
)


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    await update.message.reply_text(
f"""
🔗 Your referral link

https://t.me/{BOT_USERNAME}?start=ref_{uid}

Earn 150 points per referral
"""
)


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute("SELECT * FROM tasks")
    tasks = c.fetchall()

    if not tasks:

        await update.message.reply_text("No tasks available")

        return

    keyboard = []

    for t in tasks:

        keyboard.append(
[InlineKeyboardButton(
f"{t[1]} ({t[3]} pts)",
callback_data=f"task_{t[0]}"
)]
)

    await update.message.reply_text(
"📋 Available Tasks",
reply_markup=InlineKeyboardMarkup(keyboard)
)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if "task_" in data:

        task_id = int(data.split("_")[1])

        c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = c.fetchone()

        pending_task[query.from_user.id] = task_id

        await query.message.reply_text(
f"""
✅ Task Selected

{task[1]}

{task[2]}

Send your proof now.
"""
)


async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if uid not in pending_task:

        return

    task_id = pending_task.pop(uid)

    text = None
    file_path = None

    if update.message.photo:

        file = await update.message.photo[-1].get_file()

        file_path = f"{SUB_DIR}/{uid}_{datetime.now().timestamp()}.jpg"

        await file.download_to_drive(file_path)

    elif update.message.voice:

        file = await update.message.voice.get_file()

        file_path = f"{SUB_DIR}/{uid}_{datetime.now().timestamp()}.ogg"

        await file.download_to_drive(file_path)

    else:

        text = update.message.text

    c.execute(
"INSERT INTO submissions(user_id,task_id,file_path,text_answer,time) VALUES(?,?,?,?,?)",
(uid, task_id, file_path, text, str(datetime.now()))
)

    c.execute(
"SELECT points FROM tasks WHERE id=?",
(task_id,)
)

    reward = c.fetchone()[0]

    c.execute(
"UPDATE users SET points = points + ? WHERE id=?",
(reward, uid)
)

    conn.commit()

    await update.message.reply_text(
f"✅ Submission received!\n+{reward} points"
)


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    pts = c.fetchone()[0]

    if pts < MIN_WITHDRAW:

        await update.message.reply_text(
f"❌ Minimum withdrawal is {MIN_WITHDRAW} points"
)

        return

    pending_withdraw[uid] = True

    await update.message.reply_text(
"Send your crypto wallet address"
)


async def withdraw_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if uid not in pending_withdraw:
        return

    wallet = update.message.text

    c.execute(
"INSERT INTO withdrawals(user_id,amount,wallet,status) VALUES(?,?,?,?)",
(uid, MIN_WITHDRAW, wallet, "pending")
)

    c.execute(
"UPDATE users SET points = points - ? WHERE id=?",
(MIN_WITHDRAW, uid)
)

    conn.commit()

    pending_withdraw.pop(uid)

    await update.message.reply_text(
"✅ Withdrawal request submitted"
)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
[InlineKeyboardButton("Users", callback_data="users")],
[InlineKeyboardButton("Submissions", callback_data="subs")],
[InlineKeyboardButton("Export ZIP", callback_data="zip")]
]

    await update.message.reply_text(
"Admin Panel",
reply_markup=InlineKeyboardMarkup(keyboard)
)


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "users":

        c.execute("SELECT COUNT(*) FROM users")
        count = c.fetchone()[0]

        await query.message.reply_text(
f"👥 Total Users: {count}"
)

    if query.data == "subs":

        c.execute("SELECT COUNT(*) FROM submissions")
        count = c.fetchone()[0]

        await query.message.reply_text(
f"📊 Submissions: {count}"
)

    if query.data == "zip":

        zip_path = "submissions.zip"

        with zipfile.ZipFile(zip_path, "w") as z:

            for file in os.listdir(SUB_DIR):

                z.write(f"{SUB_DIR}/{file}")

        await query.message.reply_document(open(zip_path, "rb"))


async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    text = " ".join(context.args)

    title, pts, desc = text.split("|")

    c.execute(
"INSERT INTO tasks(title,description,points) VALUES(?,?,?)",
(title, desc, int(pts))
)

    conn.commit()

    await update.message.reply_text("✅ Task added")


def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addtask", addtask))

    app.add_handler(CallbackQueryHandler(button, pattern="task_"))
    app.add_handler(CallbackQueryHandler(admin_buttons))

    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT | filters.VOICE, submission))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_wallet))

    print("TaskHive Bot Running...")

    app.run_polling()


if __name__ == "__main__":
    main()
