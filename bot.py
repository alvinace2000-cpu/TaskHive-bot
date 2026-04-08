import os
import sqlite3
import zipfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
BOT_USERNAME = "Task_Hive"
ADMIN_ID = 8728887265
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
SUB_DIR = f"{DATA_DIR}/submissions"

os.makedirs(SUB_DIR, exist_ok=True)

conn = sqlite3.connect(f"{DATA_DIR}/taskhive.db", check_same_thread=False)
c = conn.cursor()

# USERS
c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0,
ref_by INTEGER
)
""")

# TASKS
c.execute("""
CREATE TABLE IF NOT EXISTS tasks(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
description TEXT,
points INTEGER,
limit_count INTEGER
)
""")

# SUBMISSIONS
c.execute(
    "SELECT * FROM submissions WHERE user_id=? AND task_id=?",
    (uid, task_id)
)

if c.fetchone():
    await update.message.reply_text("❌ You already completed this task.")
    return
    
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

pending_task = {}
admin_add = {}

MIN_WITHDRAW = 1500


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username or "user"

    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    res = c.fetchone()

    if not res:
        c.execute("INSERT INTO users VALUES(?,?,?,?)", (uid, username, 50, None))
        conn.commit()
        await update.message.reply_text(
f"""👋 Welcome to TaskHive @{username}

🎁 50 points bonus added

Use /tasks to start earning!
"""
)

    else:
        await update.message.reply_text(
f"""👋 Welcome back @{username}

Use /tasks to earn more points
"""
)


# POINTS
async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    user = c.fetchone()

    if not user:
        await update.message.reply_text("Use /start first")
        return

    pts = user[0]

    await update.message.reply_text(
        f"💰 Your Points Balance\n\n{pts} points"
    )


# TASK LIST
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute("SELECT * FROM tasks")
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("No tasks available")
        return

    keyboard = []

    for t in rows:

        c.execute("SELECT COUNT(*) FROM submissions WHERE task_id=?", (t[0],))
        count = c.fetchone()[0]

        if count >= t[4]:
            continue

        keyboard.append([
            InlineKeyboardButton(
                f"{t[1]} ({t[3]} pts)",
                callback_data=f"task_{t[0]}"
            )
        ])

    await update.message.reply_text(
        "📋 Available Tasks",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# TASK SELECT
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if "task_" in data:

        task_id = int(data.split("_")[1])
        uid = query.from_user.id

        c.execute(
            "SELECT * FROM submissions WHERE user_id=? AND task_id=?",
            (uid, task_id)
        )

        if c.fetchone():
            await query.message.reply_text("❌ You already completed this task")
            return

        c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = c.fetchone()

        pending_task[uid] = task_id

        await query.message.reply_text(
f"""
📌 Task

{task[1]}

{task[2]}

Send proof now
"""
)


# SUBMISSION
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
    await update.message.reply_text("❌ Task submission limit reached.")
    return
    
    c.execute(
        "INSERT INTO submissions(user_id,task_id,file_path,text_answer,time) VALUES(?,?,?,?,?)",
        (uid, task_id, file_path, text, str(datetime.now()))
    )

    c.execute("SELECT points FROM tasks WHERE id=?", (task_id,))
    reward = c.fetchone()[0]

    c.execute("UPDATE users SET points = points + ? WHERE id=?", (reward, uid))

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

[InlineKeyboardButton("📊 Submissions", callback_data="subs")],

[InlineKeyboardButton("➕ Add Task", callback_data="addtask")],

[InlineKeyboardButton("🗑 Delete Task", callback_data="deltask")],

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

        c.execute("SELECT id,username,points FROM users")

        rows = c.fetchall()

        msg = "👥 Users\n\n"

        for r in rows:
            msg += f"{r[1]} | {r[2]} pts\n"

        await query.message.reply_text(msg)


    elif data == "subs":

        c.execute("SELECT COUNT(*) FROM submissions")
        count = c.fetchone()[0]

        await query.message.reply_text(f"📊 Total submissions: {count}")


    elif data == "addtask":

        admin_add[query.from_user.id] = "title"

        await query.message.reply_text("Send task title")


    elif data == "deltask":

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


    elif "del_" in data:

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


# ADMIN ADD TASK FLOW
async def admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if uid not in admin_add:
        return

    step = admin_add[uid]

    # STEP 1 — TITLE
    if step == "title":

        context.user_data["task_title"] = update.message.text
        admin_add[uid] = "desc"

        await update.message.reply_text("Send task description")

        return

    # STEP 2 — DESCRIPTION
    if step == "desc":

        context.user_data["task_desc"] = update.message.text
        admin_add[uid] = "points"

        await update.message.reply_text("Send task reward points")

        return

    # STEP 3 — POINTS
    if step == "points":

        context.user_data["task_points"] = int(update.message.text)
        admin_add[uid] = "limit"

        await update.message.reply_text("Send submission limit")

        return

    # STEP 4 — LIMIT
    if step == "limit":

        limit = int(update.message.text)

        title = context.user_data["task_title"]
        desc = context.user_data["task_desc"]
        points = context.user_data["task_points"]

        c.execute(
            "INSERT INTO tasks(title,description,points,limit_count) VALUES(?,?,?,?)",
            (title, desc, points, limit)
        )

        conn.commit()

        admin_add.pop(uid)

        await update.message.reply_text("✅ Task added successfully")
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

        admin_add.pop(uid)

        await update.message.reply_text("✅ Task added")


# MAIN
def main():

    app = Application.builder().token(TOKEN).build()

    # COMMANDS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", profile))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("admin", admin))

    # BUTTONS
    app.add_handler(CallbackQueryHandler(button, pattern="task_"))
    app.add_handler(CallbackQueryHandler(admin_buttons))

    # ADMIN INPUT (task creation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_messages))

    # USER SUBMISSIONS
    app.add_handler(MessageHandler(filters.PHOTO, submission))
    app.add_handler(MessageHandler(filters.VOICE, submission))

    # WITHDRAW WALLET
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_wallet))

    print("TaskHive Bot Running...")
    app.run_polling()
