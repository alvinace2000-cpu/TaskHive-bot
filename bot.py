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

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8728887265
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
SUB_DIR = f"{DATA_DIR}/submissions"

os.makedirs(SUB_DIR, exist_ok=True)

conn = sqlite3.connect(f"{DATA_DIR}/taskhive.db", check_same_thread=False)
c = conn.cursor()

# DATABASE

c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS tasks(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
description TEXT,
points INTEGER,
limit_count INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS submissions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
task_id INTEGER,
file_path TEXT,
text_answer TEXT,
time TEXT
)
""")

conn.commit()

pending_tasks = {}
admin_state = {}

# START

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    uid = user.id
    username = user.username or "user"

    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    res = c.fetchone()

    if not res:

        c.execute(
        "INSERT INTO users(id,username,points) VALUES(?,?,?)",
        (uid, username, 50)
        )
        conn.commit()

        await update.message.reply_text(
f"""👋 Welcome to TaskHive @{username}

🎁 50 points bonus added

Join announcements:
{CHANNEL_LINK}

Use /tasks to start earning points."""
)

    else:

        c.execute("SELECT points FROM users WHERE id=?", (uid,))
        pts = c.fetchone()[0]

        await update.message.reply_text(
f"""👋 Welcome back @{username}

💰 Points: {pts}

Use /tasks to continue earning."""
)

# POINTS

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    row = c.fetchone()

    if not row:
        await update.message.reply_text("Use /start first")
        return

    await update.message.reply_text(f"💰 Your Points: {row[0]}")

# TASK LIST

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute("SELECT * FROM tasks")
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("No tasks available")
        return

    keyboard = []

    for task in rows:

        task_id = task[0]

        c.execute(
        "SELECT * FROM submissions WHERE user_id=? AND task_id=?",
        (update.effective_user.id, task_id)
        )

        if c.fetchone():
            continue

        keyboard.append([
        InlineKeyboardButton(
        f"{task[1]} ({task[3]} pts)",
        callback_data=f"task_{task_id}"
        )
        ])

    await update.message.reply_text(
    "📋 Available Tasks",
    reply_markup=InlineKeyboardMarkup(keyboard)
    )

# TASK BUTTON

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("task_"):

        task_id = int(data.split("_")[1])
        uid = query.from_user.id

        pending_tasks[uid] = task_id

        c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = c.fetchone()

        await query.message.reply_text(
f"""📌 Task

{task[1]}

{task[2]}

Send proof now."""
)

# SUBMISSION

async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if uid not in pending_tasks:
        return

    task_id = pending_tasks.pop(uid)

    text = None
    file_path = None

    if update.message.photo:

        file = await update.message.photo[-1].get_file()
        file_path = f"{SUB_DIR}/{uid}_{datetime.now().timestamp()}.jpg"
        await file.download_to_drive(file_path)

    else:
        text = update.message.text

    c.execute(
    "SELECT COUNT(*) FROM submissions WHERE task_id=?",
    (task_id,)
    )
    count = c.fetchone()[0]

    c.execute(
    "SELECT limit_count FROM tasks WHERE id=?",
    (task_id,)
    )
    limit = c.fetchone()[0]

    if count >= limit:

        await update.message.reply_text("❌ Task limit reached")
        return

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
    f"✅ Task completed\n+{reward} points"
    )

# ADMIN PANEL

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [

[InlineKeyboardButton("👥 Users", callback_data="users")],

[InlineKeyboardButton("➕ Add Task", callback_data="addtask")],

[InlineKeyboardButton("❌ Delete Task", callback_data="delete")],

[InlineKeyboardButton("📦 Export ZIP", callback_data="zip")]

]

    await update.message.reply_text(
    "⚙️ Admin Panel",
    reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ADMIN BUTTONS

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "users":

        c.execute("SELECT username,points FROM users")
        rows = c.fetchall()

        msg = "👥 Users\n\n"

        for r in rows:
            msg += f"{r[0]} | {r[1]} pts\n"

        await query.message.reply_text(msg)

    elif data == "addtask":

        admin_state[query.from_user.id] = "title"
        await query.message.reply_text("Send task title")

    elif data == "delete":

        c.execute("SELECT id,title FROM tasks")
        rows = c.fetchall()

        keyboard = []

        for r in rows:

            keyboard.append([
            InlineKeyboardButton(
            r[1],
            callback_data=f"del_{r[0]}"
            )
            ])

        await query.message.reply_text(
        "Select task to delete",
        reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("del_"):

        task_id = int(data.split("_")[1])

        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()

        await query.message.reply_text("Task deleted")

    elif data == "zip":

        zip_path = "submissions.zip"

        with zipfile.ZipFile(zip_path, "w") as z:

            for file in os.listdir(SUB_DIR):

                z.write(f"{SUB_DIR}/{file}")

        await query.message.reply_document(open(zip_path, "rb"))

# ADMIN TEXT FLOW

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if uid not in admin_state:
        return

    step = admin_state[uid]

    if step == "title":

        context.user_data["title"] = update.message.text
        admin_state[uid] = "desc"

        await update.message.reply_text("Send task description")

    elif step == "desc":

        context.user_data["desc"] = update.message.text
        admin_state[uid] = "points"

        await update.message.reply_text("Send reward points")

    elif step == "points":

        context.user_data["points"] = int(update.message.text)
        admin_state[uid] = "limit"

        await update.message.reply_text("Send submission limit")

    elif step == "limit":

        title = context.user_data["title"]
        desc = context.user_data["desc"]
        pts = context.user_data["points"]
        limit = int(update.message.text)

        c.execute(
        "INSERT INTO tasks(title,description,points,limit_count) VALUES(?,?,?,?)",
        (title, desc, pts, limit)
        )

        conn.commit()

        admin_state.pop(uid)

        await update.message.reply_text("✅ Task added successfully")

# MAIN

def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("admin", admin))

    app.add_handler(CallbackQueryHandler(buttons, pattern="task_"))
    app.add_handler(CallbackQueryHandler(admin_buttons))

    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, submit))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text))

    print("TaskHive Bot Running...")

    app.run_polling()

if __name__ == "__main__":
    main()
