import sqlite3
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TOKEN")

ADMIN_ID = 8728887265
MIN_WITHDRAW = 1500
REF_REWARD = 200

conn = sqlite3.connect("taskhive.db", check_same_thread=False)
c = conn.cursor()

# USERS
c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
username TEXT,
points INTEGER DEFAULT 0,
referrer INTEGER
)
""")

# TASKS
c.execute("""
CREATE TABLE IF NOT EXISTS tasks(
id INTEGER PRIMARY KEY AUTOINCREMENT,
title TEXT,
description TEXT,
reward INTEGER
)
""")

# SUBMISSIONS
c.execute("""
CREATE TABLE IF NOT EXISTS submissions(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER,
task_id INTEGER,
content TEXT
)
""")

conn.commit()


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    c.execute("SELECT * FROM users WHERE id=?", (user.id,))
    exists = c.fetchone()

    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except:
            pass

    if not exists:

        c.execute(
            "INSERT INTO users(id,username,points,referrer) VALUES(?,?,?,?)",
            (user.id, user.username, 0, ref)
        )

        if ref:
            c.execute(
                "UPDATE users SET points = points + ? WHERE id=?",
                (REF_REWARD, ref)
            )

        conn.commit()

        await update.message.reply_text(
f"""
👋 Welcome to TaskHive!

Earn points by completing simple tasks.

📢 Join announcements:
https://t.me/+6WtlEwqjwccxOTVk

Use /tasks to start earning!
"""
        )

    else:

        c.execute("SELECT points FROM users WHERE id=?", (user.id,))
        pts = c.fetchone()[0]

        await update.message.reply_text(
f"""
Welcome back @{user.username}

Your points: {pts}

Use /tasks to see available work.
"""
        )


# HELP
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
"""
Commands

/tasks – show tasks
/points – check balance
/referral – invite friends
/withdraw – withdraw points

Announcements:
https://t.me/+6WtlEwqjwccxOTVk
"""
)


# POINTS
async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    pts = c.fetchone()[0]

    await update.message.reply_text(f"💰 Your balance: {pts} points")


# TASK LIST
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    c.execute("SELECT * FROM tasks")
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("No tasks available yet.")
        return

    text = "📋 Tasks\n\n"

    for r in rows:
        text += f"""
ID: {r[0]}
{r[1]}
Reward: {r[3]} points
Submit: /submit {r[0]}
"""

    await update.message.reply_text(text)


# SUBMIT TASK
async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usage: /submit TASK_ID your answer")
        return

    task_id = context.args[0]
    content = " ".join(context.args[1:])

    c.execute("SELECT reward FROM tasks WHERE id=?", (task_id,))
    task = c.fetchone()

    if not task:
        await update.message.reply_text("Invalid task ID.")
        return

    reward = task[0]

    c.execute(
        "INSERT INTO submissions(user_id,task_id,content) VALUES(?,?,?)",
        (uid, task_id, content)
    )

    c.execute(
        "UPDATE users SET points = points + ? WHERE id=?",
        (reward, uid)
    )

    conn.commit()

    await update.message.reply_text(f"✅ Task submitted! You earned {reward} points.")


# REFERRAL
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    bot = await context.bot.get_me()

    link = f"https://t.me/{bot.username}?start={uid}"

    await update.message.reply_text(
f"""
Invite friends and earn {REF_REWARD} points.

Your link:
{link}
"""
)


# WITHDRAW
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    pts = c.fetchone()[0]

    if pts < MIN_WITHDRAW:
        await update.message.reply_text(
f"Minimum withdrawal is {MIN_WITHDRAW} points."
        )
        return

    await update.message.reply_text("Withdrawal request sent to admin.")


# ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
"""
Admin Panel

/addtask title | description | reward
/deletetask id
/users
/submissions
"""
)


# ADD TASK
async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    try:
        data = " ".join(context.args).split("|")

        title = data[0].strip()
        desc = data[1].strip()
        reward = int(data[2].strip())

        c.execute(
            "INSERT INTO tasks(title,description,reward) VALUES(?,?,?)",
            (title, desc, reward)
        )

        conn.commit()

        await update.message.reply_text("Task added successfully.")

    except:
        await update.message.reply_text(
"Format:\n/addtask Title | Description | Reward"
        )


# DELETE TASK
async def deletetask(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    tid = context.args[0]

    c.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()

    await update.message.reply_text("Task deleted.")


# USERS
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]

    await update.message.reply_text(f"Total users: {total}")


# SUBMISSIONS
async def submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    c.execute("SELECT COUNT(*) FROM submissions")
    total = c.fetchone()[0]

    await update.message.reply_text(f"Total submissions: {total}")


# MAIN
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("submit", submit))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("withdraw", withdraw))

    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("deletetask", deletetask))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("submissions", submissions))

    app.run_polling()


if __name__ == "__main__":
    main()
