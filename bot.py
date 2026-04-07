import os
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")

CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

# DATABASE
conn = sqlite3.connect("taskhive.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
telegram_id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0
)
""")

conn.commit()


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else f"user{user_id}"

    # referral id
    referrer = None
    if context.args:
        referrer = context.args[0]

    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
    data = cursor.fetchone()

    if data:
        points = data[2]

        await update.message.reply_text(
            f"👋 Welcome back @{username}\n\n"
            f"💰 Points: {points}\n\n"
            "Use /tasks to earn more."
        )

    else:

        cursor.execute(
            "INSERT INTO users (telegram_id,username,points) VALUES (?,?,?)",
            (user_id, username, 50),
        )
        conn.commit()

        # reward referrer
        if referrer and int(referrer) != user_id:

            cursor.execute(
                "UPDATE users SET points = points + 100 WHERE telegram_id=?",
                (referrer,),
            )
            conn.commit()

        await update.message.reply_text(
            "🎉 Welcome to TaskHive!\n\n"
            "Earn points by completing tasks.\n\n"
            f"Join channel:\n{CHANNEL_LINK}\n\n"
            "Use /tasks to start."
        )


# HELP
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "TaskHive Commands\n\n"
        "/start - Start bot\n"
        "/tasks - View tasks\n"
        "/points - Check balance\n"
        "/help - Show help\n\n"
        f"Channel:\n{CHANNEL_LINK}"
    )


# POINTS
async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    cursor.execute("SELECT points FROM users WHERE telegram_id=?", (user_id,))
    data = cursor.fetchone()

    if data:
        await update.message.reply_text(f"💰 Your points: {data[0]}")
    else:
        await update.message.reply_text("Use /start first.")


# TASKS
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Available Tasks\n\n"
        "1️⃣ Take a local photo\n"
        "2️⃣ Record voice describing your area\n"
        "3️⃣ Write local food prices\n\n"
        "Use /submit to send task result."
    )


# SUBMIT
async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    cursor.execute(
        "UPDATE users SET points = points + 40 WHERE telegram_id=?",
        (user_id,),
    )

    conn.commit()

    await update.message.reply_text(
        "✅ Submission received.\n\n"
        "You earned 40 points."
    )

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    referral_link = f"https://t.me/Task_Hive_bot?start={user_id}"

    await update.message.reply_text(
        f"👥 Your referral link:\n\n{referral_link}\n\n"
        "Invite friends and earn 100 points for each signup."
    )

# MAIN
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("submit", submit))

    print("TaskHive Bot Running")

    app.run_polling()


if __name__ == "__main__":
    main()
