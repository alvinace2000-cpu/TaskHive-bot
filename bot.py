# ==========================
# TaskHive Ultimate Bot
# ==========================
import os
import sqlite3
import zipfile
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --------------------------
# CONFIG
# --------------------------
TOKEN = "8621802384:AAFzLeM96MvmHNBHDoS3nyNh9wCrH_3MHFY"
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"
ADMIN_ID = 8728887265
MIN_WITHDRAW_POINTS = 1500

# --------------------------
# DATABASE SETUP
# --------------------------
conn = sqlite3.connect("taskhive.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    type TEXT,
    reward INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    user_id INTEGER,
    type TEXT,
    content TEXT
)
""")
conn.commit()

# --------------------------
# COMMAND HANDLERS
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else f"user{user_id}"

    # referral
    referrer = None
    if context.args:
        referrer = int(context.args[0])

    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
    data = cursor.fetchone()

    if data:
        points = data[2]
        await update.message.reply_text(
            f"👋 Welcome back @{username}!\n"
            f"💰 Points: {points}\n\n"
            "Use /tasks to earn more points."
        )
    else:
        cursor.execute("INSERT INTO users (telegram_id, username, points) VALUES (?, ?, ?)", (user_id, username, 50))
        conn.commit()

        if referrer and referrer != user_id:
            cursor.execute("UPDATE users SET points = points + 100, referrals = referrals + 1 WHERE telegram_id=?", (referrer,))
            conn.commit()

        await update.message.reply_text(
            f"🎉 Welcome to TaskHive @{username}!\n\n"
            f"Earn points by completing tasks.\n"
            f"Join announcements:\n{CHANNEL_LINK}\n\n"
            "Use /tasks to start earning points!"
        )

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_link = f"https://t.me/Task_Hive_bot?start={user_id}"
    await update.message.reply_text(
        f"👥 Your referral link:\n{referral_link}\nInvite friends to earn 100 points each!"
    )

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT points FROM users WHERE telegram_id=?", (user_id,))
    data = cursor.fetchone()
    if data:
        await update.message.reply_text(f"💰 You have {data[0]} points.")
    else:
        await update.message.reply_text("❌ User not found. Use /start first.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 TaskHive Commands:\n"
        "/start - Welcome message\n"
        "/tasks - View tasks\n"
        "/points - Check your points\n"
        "/refer - Your referral link\n"
        "/help - Show this help\n"
        f"Announcements: {CHANNEL_LINK}"
    )

# --------------------------
# ADMIN COMMANDS
# --------------------------
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not admin.")
        return

    await update.message.reply_text(
        "🛠 TaskHive Admin Panel\n"
        "/users - Show all users\n"
        "/stats - Platform stats\n"
        "/addtask - Add task\n"
        "/edittask - Edit task\n"
        "/deletetask - Delete task\n"
        "/submissions - View submissions"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tasks")
    total_tasks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM submissions")
    total_submissions = cursor.fetchone()[0]
    await update.message.reply_text(
        f"📊 Stats\nUsers: {total_users}\nTasks: {total_tasks}\nSubmissions: {total_submissions}"
    )

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT username, points, referrals FROM users")
    rows = cursor.fetchall()
    msg = "👥 Users:\n"
    for r in rows:
        msg += f"{r[0]} | Points: {r[1]} | Referrals: {r[2]}\n"
    await update.message.reply_text(msg)

# --------------------------
# MAIN SETUP
# --------------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # USER COMMANDS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refer", refer))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("help", help_command))
    
    # ADMIN COMMANDS
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", users))

    print("🚀 TaskHive bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
