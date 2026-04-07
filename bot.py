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

ADMIN_ID = 8728887265
BOT_USERNAME = "TaskHiveDataBot"
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
SUBMISSIONS_DIR = os.path.join(DATA_DIR, "submissions")

os.makedirs(SUBMISSIONS_DIR, exist_ok=True)

# DATABASE
conn = sqlite3.connect(os.path.join(DATA_DIR, "taskhive.db"), check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
telegram_id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0,
referrer INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS submissions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
task_id TEXT,
file_path TEXT,
text_answer TEXT,
status TEXT,
timestamp TEXT
)
""")

conn.commit()

# TASK LIST
TASKS = {
    "1": {
        "name": "📷 Local Photo",
        "points": 40,
        "desc": "Take a photo of your surroundings"
    },
    "2": {
        "name": "🎙 Voice Description",
        "points": 80,
        "desc": "Send 10 second voice describing your area"
    },
    "3": {
        "name": "📝 Price Survey",
        "points": 50,
        "desc": "Tell us prices of rice, sugar, bread"
    }
}

user_pending = {}

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id
    username = user.username or f"user{user_id}"

    referrer = None

    if context.args:
        if "ref_" in context.args[0]:
            referrer = int(context.args[0].split("_")[1])

    c.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
    exists = c.fetchone()

    if not exists:

        c.execute(
            "INSERT INTO users VALUES (?,?,?,?)",
            (user_id, username, 50, referrer)
        )

        conn.commit()

        if referrer:
            c.execute(
                "UPDATE users SET points = points + 150 WHERE telegram_id=?",
                (referrer,)
            )
            conn.commit()

        await update.message.reply_text(
            f"👋 Welcome {username}\n\n"
            f"You received 50 bonus points\n\n"
            f"Use /tasks to start"
        )

    else:

        await update.message.reply_text(
            "Welcome back!\nUse /tasks"
        )

# TASK LIST
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = []

    for key, task in TASKS.items():

        keyboard.append([
            InlineKeyboardButton(
                f"{task['name']} — {task['points']} pts",
                callback_data=f"task_{key}"
            )
        ])

    await update.message.reply_text(
        "📋 Available Tasks",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# TASK BUTTON
async def task_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    task_id = query.data.split("_")[1]
    task = TASKS[task_id]

    user_pending[query.from_user.id] = task_id

    await query.edit_message_text(
        f"{task['name']}\n\n{task['desc']}\n\nSend submission now"
    )

# SUBMISSION HANDLER
async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in user_pending:
        return

    task_id = user_pending.pop(user_id)

    file_path = None
    text_answer = None

    if update.message.photo:

        file = await update.message.photo[-1].get_file()

        file_path = os.path.join(
            SUBMISSIONS_DIR,
            f"{user_id}_{datetime.now().timestamp()}.jpg"
        )

        await file.download_to_drive(file_path)

    elif update.message.voice:

        file = await update.message.voice.get_file()

        file_path = os.path.join(
            SUBMISSIONS_DIR,
            f"{user_id}_{datetime.now().timestamp()}.ogg"
        )

        await file.download_to_drive(file_path)

    else:

        text_answer = update.message.text

    c.execute(
        """INSERT INTO submissions
        (user_id,task_id,file_path,text_answer,status,timestamp)
        VALUES (?,?,?,?,?,?)""",
        (
            user_id,
            task_id,
            file_path,
            text_answer,
            "pending",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        )
    )

    conn.commit()

    await update.message.reply_text(
        "✅ Submission received!\nWaiting admin approval."
    )

# ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
        [InlineKeyboardButton("👥 Users", callback_data="users")],
        [InlineKeyboardButton("📥 Submissions", callback_data="subs")],
        [InlineKeyboardButton("📦 Download ZIP", callback_data="zip")]
    ]

    await update.message.reply_text(
        "Admin Panel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ADMIN CALLBACK
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "users":

        c.execute("SELECT username,points FROM users ORDER BY points DESC")

        rows = c.fetchall()

        text = "Leaderboard\n\n"

        for r in rows:

            text += f"{r[0]} — {r[1]} pts\n"

        await query.edit_message_text(text)

    elif data == "subs":

        c.execute(
            "SELECT id,user_id,task_id FROM submissions WHERE status='pending'"
        )

        rows = c.fetchall()

        text = "Pending Submissions\n\n"

        for r in rows:

            text += f"ID {r[0]} | User {r[1]} | Task {r[2]}\n"

        await query.edit_message_text(text)

    elif data == "zip":

        zip_path = os.path.join(DATA_DIR, "submissions.zip")

        with zipfile.ZipFile(zip_path, "w") as z:

            for f in os.listdir(SUBMISSIONS_DIR):

                z.write(os.path.join(SUBMISSIONS_DIR, f), f)

        await query.message.reply_document(
            open(zip_path, "rb"),
            filename="submissions.zip"
        )

# POINTS
async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    c.execute(
        "SELECT points FROM users WHERE telegram_id=?",
        (user_id,)
    )

    pts = c.fetchone()

    if pts:
        pts = pts[0]
    else:
        pts = 0

    await update.message.reply_text(
        f"💰 Points: {pts}"
    )

# LEADERBOARD
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute(
        "SELECT username,points FROM users ORDER BY points DESC LIMIT 10"
    )

    rows = c.fetchall()

    text = "🏆 Top Users\n\n"

    for i, r in enumerate(rows):

        text += f"{i+1}. {r[0]} — {r[1]} pts\n"

    await update.message.reply_text(text)

# REFERRAL
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

    await update.message.reply_text(
        f"Invite friends and earn 150 pts\n\n{link}"
    )

# MAIN
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("admin", admin))

    app.add_handler(
        CallbackQueryHandler(task_button, pattern="task_")
    )

    app.add_handler(
        CallbackQueryHandler(admin_callback)
    )

    app.add_handler(
        MessageHandler(filters.ALL, submission)
    )

    print("BOT RUNNING")

    app.run_polling()

if __name__ == "__main__":
    main()
