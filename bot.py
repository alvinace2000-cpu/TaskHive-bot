import sqlite3
import os
import zipfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("TOKEN")
BOT_USERNAME = "TaskHiveDataBot"
ADMIN_ID = 8728887265

MIN_WITHDRAW = 1500
NEW_USER_BONUS = 50
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
SUBMISSIONS_DIR = os.path.join(DATA_DIR, "submissions")
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)

conn = sqlite3.connect(os.path.join(DATA_DIR, "taskhive.db"), check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_type TEXT, timestamp TEXT, file_path TEXT, text_answer TEXT)''')
conn.commit()

TASKS = {
    "1": {"name": "📷 Local Photo", "points": 40, "desc": "Take one clear photo of your surroundings."},
    "2": {"name": "🎙️ Voice Description", "points": 80, "desc": "Record 10-15 second voice note describing what you see."},
    "3": {"name": "📝 Local Prices Survey", "points": 50, "desc": "Tell us current prices: 1kg rice, 1kg sugar, loaf of bread, plate of ugali + meat."},
    "4": {"name": "🍲 Popular Local Food", "points": 40, "desc": "What is the most popular food/drink in your area?"},
    "5": {"name": "🔄 English to Swahili Translation", "points": 70, "desc": "Translate 5 simple English sentences."}
}

user_pending = {}
admin_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"

    c.execute("SELECT points FROM users WHERE telegram_id = ?", (user_id,))
    result = c.fetchone()

    if result:
        pts = result[0]
        await update.message.reply_text(f"👋 Welcome back, @{username}!\nYou currently have **{pts} points**.\n\nUse /tasks to continue earning.")
    else:
        c.execute("INSERT INTO users (telegram_id, username, points) VALUES (?, ?, ?)", (user_id, username, NEW_USER_BONUS))
        conn.commit()
        await update.message.reply_text(f"👋 Welcome to TaskHive, @{username}!\nYou received **{NEW_USER_BONUS} bonus points**!\n\nJoin channel: {CHANNEL_LINK}\nUse /tasks to start.")

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(f"{task['name']} — {task['points']} pts", callback_data=key)] for key, task in TASKS.items()]
    await update.message.reply_text("📋 Available Tasks", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = query.data
    task = TASKS[task_id]

    c.execute("SELECT * FROM submissions WHERE user_id = ? AND task_type = ?", (query.from_user.id, task_id))
    if c.fetchone():
        await query.edit_message_text("❌ You have already completed this task.")
        return

    user_pending[query.from_user.id] = task_id
    await query.edit_message_text(f"✅ Task: {task['name']}\n\n{task['desc']}\n\nSend your response now.")

async def handle_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_pending:
        return
    task_id = user_pending.pop(user_id)
    task = TASKS[task_id]

    file_path = None
    text_answer = None

    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_path = os.path.join(SUBMISSIONS_DIR, f"{user_id}_photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        await file.download_to_drive(file_path)
    elif update.message.voice:
        file = await update.message.voice.get_file()
        file_path = os.path.join(SUBMISSIONS_DIR, f"{user_id}_voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg")
        await file.download_to_drive(file_path)
    else:
        text_answer = update.message.text

    c.execute("INSERT INTO submissions (user_id, task_type, timestamp, file_path, text_answer) VALUES (?, ?, ?, ?, ?)",
              (user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M"), file_path, text_answer))
    c.execute("UPDATE users SET points = points + ? WHERE telegram_id = ?", (task["points"], user_id))
    conn.commit()

    await update.message.reply_text(f"✅ Task completed!\nYou earned +{task['points']} points!")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT points FROM users WHERE telegram_id = ?", (user_id,))
    result = c.fetchone()
    pts = result[0] if result else 0
    await update.message.reply_text(f"💰 Your current points: **{pts}**")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔗 Your referral link:\nhttps://t.me/{BOT_USERNAME}?start=ref_{update.effective_user.id}\n\nShare and earn 150 points per friend!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 TaskHive Commands:\n"
        "/start - Welcome message\n"
        "/tasks - See available tasks\n"
        "/points - Check your points\n"
        "/referral - Get your referral link\n"
        "/help - This message\n\n"
        "📢 Join our Announcement Channel:\n" + CHANNEL_LINK
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return

    # Show current tasks list for easy editing/deleting
    task_list = "\n".join([f"ID {k}: {v['name']} ({v['points']} pts)" for k, v in TASKS.items()])

    keyboard = [
        [InlineKeyboardButton("👥 Users & Points", callback_data="view_users")],
        [InlineKeyboardButton("📊 Submissions Summary", callback_data="view_submissions")],
        [InlineKeyboardButton("➕ Add New Task", callback_data="add_task")],
        [InlineKeyboardButton("✏️ Edit Task", callback_data="edit_task")],
        [InlineKeyboardButton("🗑 Delete Task", callback_data="delete_task")],
        [InlineKeyboardButton("📥 Download All Files (ZIP)", callback_data="download_zip")]
    ]

    await update.message.reply_text(f"🔧 **Admin Panel**\n\nCurrent Tasks:\n{task_list}", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "download_zip":
        files = [f for f in os.listdir(SUBMISSIONS_DIR) if os.path.isfile(os.path.join(SUBMISSIONS_DIR, f))]
        if not files:
            await query.edit_message_text("No files yet.")
            return
        zip_path = os.path.join(DATA_DIR, "TaskHive_All_Files.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for f in files:
                zipf.write(os.path.join(SUBMISSIONS_DIR, f), f)
        await query.message.reply_document(open(zip_path, 'rb'), filename="TaskHive_All_Files.zip")
        os.remove(zip_path)

    elif query.data == "view_users":
        c.execute("SELECT username, points FROM users ORDER BY points DESC")
        rows = c.fetchall()
        text = f"👥 Users & Points ({len(rows)} total)\n\n"
        for row in rows:
            text += f"• @{row[0]} → {row[1]} pts\n"
        await query.edit_message_text(text)

    elif query.data == "view_submissions":
        c.execute("SELECT COUNT(*) FROM submissions")
        total = c.fetchone()[0]
        files = len([f for f in os.listdir(SUBMISSIONS_DIR) if os.path.isfile(os.path.join(SUBMISSIONS_DIR, f))])
        await query.edit_message_text(f"📊 Submissions Summary\nTotal Submissions: {total}\nTotal Files: {files}")

    elif query.data == "add_task":
        await query.edit_message_text("➕ Send new task in format:\n`Name|Points|Description`")
        admin_state[query.from_user.id] = "add"

    elif query.data == "edit_task":
        await query.edit_message_text("✏️ Send in format:\n`ID|NewName|NewPoints|NewDescription`")
        admin_state[query.from_user.id] = "edit"

    elif query.data == "delete_task":
        await query.edit_message_text("🗑 Send the Task ID you want to delete.")
        admin_state[query.from_user.id] = "delete"

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in admin_state:
        return

    mode = admin_state.pop(user_id)

    if mode == "add":
        try:
            name, points, desc = [x.strip() for x in text.split("|", 2)]
            task_id = str(len(TASKS) + 1)
            TASKS[task_id] = {"name": name, "points": int(points), "desc": desc}
            await update.message.reply_text(f"✅ New task added!\nID: {task_id}")
        except:
            await update.message.reply_text("❌ Wrong format. Use `Name|Points|Description`")

    elif mode == "edit":
        try:
            task_id, name, points, desc = [x.strip() for x in text.split("|", 3)]
            if task_id in TASKS:
                TASKS[task_id] = {"name": name, "points": int(points), "desc": desc}
                await update.message.reply_text(f"✅ Task {task_id} updated!")
            else:
                await update.message.reply_text("❌ Task ID not found.")
        except:
            await update.message.reply_text("❌ Wrong format. Use `ID|NewName|NewPoints|NewDescription`")

    elif mode == "delete":
        if text in TASKS:
            del TASKS[text]
            await update.message.reply_text(f"✅ Task {text} deleted!")
        else:
            await update.message.reply_text("❌ Task ID not found.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.ALL, handle_submission))
    print("🚀 TaskHive is LIVE with FULL Admin Buttons!")
    app.run_polling()

if __name__ == "__main__":
    main()
