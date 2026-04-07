import os
import sqlite3
import zipfile
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TOKEN")

BOT_USERNAME = "TaskHiveDataBot"
ADMIN_ID = 8728887265
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
FILES_DIR = os.path.join(DATA_DIR, "submissions")

os.makedirs(FILES_DIR, exist_ok=True)

conn = sqlite3.connect(os.path.join(DATA_DIR, "taskhive.db"), check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
telegram_id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0,
ref_by INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS tasks(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
description TEXT,
points INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS submissions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
task_id INTEGER,
timestamp TEXT,
file_path TEXT,
text_answer TEXT
)
""")

conn.commit()

user_pending = {}

# ------------------------------------------------
# START COMMAND
# ------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id
    username = user.username or f"user_{user_id}"

    ref = None

    if context.args:
        if "ref_" in context.args[0]:
            ref = int(context.args[0].split("_")[1])

    c.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
    exists = c.fetchone()

    if not exists:

        c.execute(
            "INSERT INTO users (telegram_id, username, points, ref_by) VALUES (?,?,?,?)",
            (user_id, username, 50, ref)
        )

        conn.commit()

        if ref and ref != user_id:
            c.execute("UPDATE users SET points = points + 150 WHERE telegram_id=?", (ref,))
            conn.commit()

        await update.message.reply_text(
            f"""
👋 Welcome to TaskHive!

TaskHive lets you earn points by completing simple tasks like:

📷 Taking photos
🎙 Recording voice notes
📝 Completing surveys

🎁 You received 50 bonus points!

📢 Join our channel:
{CHANNEL_LINK}

Use /tasks to start earning!
"""
        )

    else:

        c.execute("SELECT points FROM users WHERE telegram_id=?", (user_id,))
        points = c.fetchone()[0]

        await update.message.reply_text(
            f"""
👋 Welcome back @{username}

💰 Your points: {points}

Use /tasks to continue earning.
"""
        )


# ------------------------------------------------
# TASK LIST
# ------------------------------------------------

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute("SELECT * FROM tasks")
    rows = c.fetchall()

    keyboard = []

    for t in rows:
        keyboard.append(
            [InlineKeyboardButton(f"{t[1]} — {t[3]} pts", callback_data=f"task_{t[0]}")]
        )

    await update.message.reply_text(
        "📋 Available Tasks",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ------------------------------------------------
# TASK SELECT
# ------------------------------------------------

async def task_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    task_id = int(query.data.split("_")[1])

    c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    task = c.fetchone()

    user_pending[query.from_user.id] = task_id

    await query.edit_message_text(
        f"""
✅ {task[1]}

{task[2]}

Send your answer now.
"""
    )


# ------------------------------------------------
# SUBMISSION HANDLER
# ------------------------------------------------

async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in user_pending:
        return

    task_id = user_pending.pop(user_id)

    c.execute("SELECT points FROM tasks WHERE id=?", (task_id,))
    points = c.fetchone()[0]

    file_path = None
    text_answer = None

    if update.message.photo:

        file = await update.message.photo[-1].get_file()

        file_path = os.path.join(
            FILES_DIR,
            f"{user_id}_{datetime.now().timestamp()}.jpg"
        )

        await file.download_to_drive(file_path)

    elif update.message.voice:

        file = await update.message.voice.get_file()

        file_path = os.path.join(
            FILES_DIR,
            f"{user_id}_{datetime.now().timestamp()}.ogg"
        )

        await file.download_to_drive(file_path)

    else:

        text_answer = update.message.text

    c.execute(
        "INSERT INTO submissions (user_id, task_id, timestamp, file_path, text_answer) VALUES (?,?,?,?,?)",
        (
            user_id,
            task_id,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            file_path,
            text_answer
        )
    )

    c.execute(
        "UPDATE users SET points = points + ? WHERE telegram_id=?",
        (points, user_id)
    )

    conn.commit()

    await update.message.reply_text(
        f"✅ Submission received!\nYou earned {points} points."
    )


# ------------------------------------------------
# POINTS
# ------------------------------------------------

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    c.execute("SELECT points FROM users WHERE telegram_id=?", (user_id,))
    pts = c.fetchone()[0]

    await update.message.reply_text(f"💰 Your points: {pts}")


# ------------------------------------------------
# REFERRAL
# ------------------------------------------------

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    await update.message.reply_text(
        f"""
Invite friends and earn 150 points!

Your link:

https://t.me/{BOT_USERNAME}?start=ref_{user_id}
"""
    )


# ------------------------------------------------
# HELP
# ------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
TaskHive Commands

/start
/tasks
/points
/referral
/help

📢 Channel:
{CHANNEL_LINK}
"""
    )


# ------------------------------------------------
# ADMIN PANEL
# ------------------------------------------------

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [

        [InlineKeyboardButton("👥 Users", callback_data="users")],
        [InlineKeyboardButton("📊 Submissions", callback_data="subs")],
        [InlineKeyboardButton("➕ Add Task", callback_data="addtask")],
        [InlineKeyboardButton("📥 Download Files", callback_data="zip")]

    ]

    await update.message.reply_text(
        "Admin Panel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ------------------------------------------------
# ADMIN CALLBACKS
# ------------------------------------------------

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "users":

        c.execute("SELECT username, points FROM users ORDER BY points DESC")
        rows = c.fetchall()

        text = f"Total Users: {len(rows)}\n\n"

        for r in rows:
            text += f"@{r[0]} — {r[1]} pts\n"

        await query.edit_message_text(text)

    if query.data == "subs":

        c.execute("SELECT COUNT(*) FROM submissions")
        total = c.fetchone()[0]

        await query.edit_message_text(f"Total submissions: {total}")

    if query.data == "zip":

        zip_path = os.path.join(DATA_DIR, "files.zip")

        with zipfile.ZipFile(zip_path, 'w') as z:

            for f in os.listdir(FILES_DIR):
                z.write(os.path.join(FILES_DIR, f), f)

        await query.message.reply_document(open(zip_path, "rb"))

        os.remove(zip_path)


# ------------------------------------------------
# MAIN
# ------------------------------------------------

def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))

    app.add_handler(CallbackQueryHandler(task_button, pattern="task_"))
    app.add_handler(CallbackQueryHandler(admin_buttons))

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VOICE, submission))

    print("Bot running...")

    app.run_polling()


if __name__ == "__main__":
    main()
