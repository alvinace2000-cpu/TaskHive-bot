import sqlite3
import logging
import os
import zipfile

from telegram import Update
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
filters,
ContextTypes
)

TOKEN = os.getenv("TOKEN")

ADMIN_ID = 8728887265
REFERRAL_REWARD = 200
MIN_WITHDRAW = 1500

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("taskhive.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0,
referrer INTEGER
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
file_id TEXT,
text TEXT
)""")

conn.commit()


def add_user(user_id, username, referrer=None):

    c.execute("SELECT id FROM users WHERE id=?", (user_id,))
    if c.fetchone():
        return False

    c.execute(
    "INSERT INTO users(id,username,points,referrer) VALUES(?,?,?,?)",
    (user_id, username, 0, referrer)
    )

    if referrer:
        c.execute(
        "UPDATE users SET points = points + ? WHERE id=?",
        (REFERRAL_REWARD, referrer)
        )

    conn.commit()

    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    ref = None

    if context.args:
        ref = int(context.args[0])

    new = add_user(user.id, user.username, ref)

    if new:

        await update.message.reply_text(
f"""
👋 Welcome to TaskHive!

Earn points by completing tasks.

📢 Join announcements:
https://t.me/+6WtlEwqjwccxOTVk

Use /tasks to start earning.
"""
)

    else:

        c.execute("SELECT points FROM users WHERE id=?", (user.id,))
        pts = c.fetchone()[0]

        await update.message.reply_text(
f"""
👋 Welcome back @{user.username}

Your points: {pts}

Use /tasks to find new tasks.
"""
)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
"""
📘 TaskHive Help

Commands:

/tasks — view tasks
/points — view balance
/referral — invite friends
/daily — daily bonus
/leaderboard — top users
/withdraw — request withdrawal

📢 Announcements
https://t.me/+6WtlEwqjwccxOTVk
"""
)


async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    pts = c.fetchone()[0]

    await update.message.reply_text(
f"💰 You have {pts} points."
)


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute("SELECT * FROM tasks")

    tasks = c.fetchall()

    if not tasks:
        await update.message.reply_text("No tasks available.")
        return

    text = "📋 Available Tasks\n\n"

    for t in tasks:
        text += f"""
ID: {t[0]}
{t[1]}
Reward: {t[3]} pts
"""

    await update.message.reply_text(text)


async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    try:

        title = context.args[0]
        points = int(context.args[1])
        desc = " ".join(context.args[2:])

        c.execute(
        "INSERT INTO tasks(title,description,points) VALUES(?,?,?)",
        (title, desc, points)
        )

        conn.commit()

        await update.message.reply_text("✅ Task added")

    except:
        await update.message.reply_text(
"Usage:\n/addtask TITLE POINTS DESCRIPTION"
)


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if update.message.photo:

        file_id = update.message.photo[-1].file_id

        c.execute(
        "INSERT INTO submissions(user_id,file_id) VALUES(?,?)",
        (uid, file_id)
        )

    elif update.message.voice:

        file_id = update.message.voice.file_id

        c.execute(
        "INSERT INTO submissions(user_id,file_id) VALUES(?,?)",
        (uid, file_id)
        )

    else:

        text = update.message.text

        c.execute(
        "INSERT INTO submissions(user_id,text) VALUES(?,?)",
        (uid, text)
        )

    c.execute(
    "UPDATE users SET points = points + 120 WHERE id=?",
    (uid,)
    )

    conn.commit()

    await update.message.reply_text(
"✅ Submission received. Points added."
)


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    bot = await context.bot.get_me()

    link = f"https://t.me/{bot.username}?start={uid}"

    await update.message.reply_text(
f"""
Invite friends and earn {REFERRAL_REWARD} points.

Your link:
{link}
"""
)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute(
    "SELECT username,points FROM users ORDER BY points DESC LIMIT 10"
    )

    rows = c.fetchall()

    text = "🏆 Leaderboard\n\n"

    i = 1

    for r in rows:
        text += f"{i}. @{r[0]} — {r[1]} pts\n"
        i += 1

    await update.message.reply_text(text)


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute(
    "UPDATE users SET points = points + 50 WHERE id=?",
    (uid,)
    )

    conn.commit()

    await update.message.reply_text("🎁 Daily reward: 50 points")


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    pts = c.fetchone()[0]

    if pts < MIN_WITHDRAW:

        await update.message.reply_text(
f"Minimum withdrawal is {MIN_WITHDRAW} points."
)

        return

    await update.message.reply_text(
"💸 Withdrawal request received. Admin will review."
)


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]

    await update.message.reply_text(
f"👥 Total users: {total}"
)


def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("users", users))

    app.add_handler(
        MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VOICE,
        submit
        )
    )

    print("TaskHive God Core running...")

    app.run_polling()


if __name__ == "__main__":
    main()
