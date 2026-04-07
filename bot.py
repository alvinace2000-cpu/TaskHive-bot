import sqlite3
import zipfile
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "YOUR_BOT_TOKEN"
ADMIN_ID = 8728887265
MIN_WITHDRAW = 1500

# DATABASE
conn = sqlite3.connect("taskhive.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, points INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, reward INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER, answer TEXT)")
conn.commit()

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    uid = user.id
    username = user.username

    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user_data = cur.fetchone()

    if not user_data:

        cur.execute("INSERT INTO users VALUES (?,?,?)",(uid,username,0))
        conn.commit()

        text = f"""
🔥 Welcome to TaskHive {username}

Earn points by completing AI training tasks.

Commands:
/tasks
/points
/help
/refer
/withdraw

Announcements:
https://t.me/+6WtlEwqjwccxOTVk
"""

    else:

        points = user_data[2]

        text = f"""
Welcome back {username}

Points: {points}

Use /tasks to earn more.
"""

    await update.message.reply_text(text)


# HELP
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
TaskHive Help

/tasks – View tasks
/submit – Submit task
/points – Check balance
/refer – Get referral link
/withdraw – Request withdrawal

Announcements:
https://t.me/+6WtlEwqjwccxOTVk
"""

    await update.message.reply_text(text)


# POINTS
async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    cur.execute("SELECT points FROM users WHERE id=?", (uid,))
    result = cur.fetchone()

    if result:
        await update.message.reply_text(f"Your balance: {result[0]} points")
    else:
        await update.message.reply_text("User not registered.")


# TASKS
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cur.execute("SELECT * FROM tasks")
    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("No tasks available.")
        return

    text = "📋 Available Tasks\n\n"

    for t in rows:
        text += f"Task {t[0]}\n{t[1]}\nReward: {t[2]} points\n\n"

    text += "Submit using:\n/submit TASK_ID answer"

    await update.message.reply_text(text)


# SUBMIT
async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    try:

        task_id = int(context.args[0])
        answer = " ".join(context.args[1:])

    except:

        await update.message.reply_text("Usage:\n/submit TASK_ID answer")
        return

    cur.execute("SELECT reward FROM tasks WHERE id=?", (task_id,))
    reward = cur.fetchone()

    if not reward:
        await update.message.reply_text("Task not found.")
        return

    cur.execute("INSERT INTO submissions(user_id,task_id,answer) VALUES(?,?,?)",(uid,task_id,answer))
    cur.execute("UPDATE users SET points = points + ? WHERE id=?",(reward[0],uid))
    conn.commit()

    await update.message.reply_text("Submission received. Points added!")


# REFERRAL
async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    link = f"https://t.me/Task_Hive?start={uid}"

    await update.message.reply_text(f"Invite friends:\n{link}\nEarn 200 points per referral.")


# WITHDRAW
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    cur.execute("SELECT points FROM users WHERE id=?", (uid,))
    points = cur.fetchone()[0]

    if points < MIN_WITHDRAW:

        await update.message.reply_text(
            f"Minimum withdrawal: {MIN_WITHDRAW}\nYour balance: {points}"
        )

        return

    await update.message.reply_text(
        "Withdrawal request received. Admin will contact you."
    )


# ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    text = """
ADMIN PANEL

/addtask title | reward
/deletetask id
/users
/submissions
/export
"""

    await update.message.reply_text(text)


# ADD TASK
async def addtask(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    try:

        data = " ".join(context.args).split("|")

        title = data[0].strip()
        reward = int(data[1].strip())

        cur.execute("INSERT INTO tasks(title,reward) VALUES(?,?)",(title,reward))
        conn.commit()

        await update.message.reply_text("Task added.")

    except:

        await update.message.reply_text("Format:\n/addtask Task name | reward")


# DELETE TASK
async def deletetask(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    tid = context.args[0]

    cur.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()

    await update.message.reply_text("Task deleted.")


# USERS
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    await update.message.reply_text(f"Total users: {total}")


# SUBMISSIONS
async def submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT * FROM submissions LIMIT 10")
    rows = cur.fetchall()

    text = ""

    for r in rows:
        text += f"User {r[1]} Task {r[2]}\n{r[3]}\n\n"

    await update.message.reply_text(text)


# EXPORT
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT * FROM submissions")
    rows = cur.fetchall()

    with open("submissions.txt","w") as f:

        for r in rows:
            f.write(str(r)+"\n")

    zipf = zipfile.ZipFile("submissions.zip","w")
    zipf.write("submissions.txt")
    zipf.close()

    await update.message.reply_document(open("submissions.zip","rb"))


# MAIN
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("submit", submit))
    app.add_handler(CommandHandler("refer", refer))
    app.add_handler(CommandHandler("withdraw", withdraw))

    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("deletetask", deletetask))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("submissions", submissions))
    app.add_handler(CommandHandler("export", export))

    print("TaskHive Bot Running...")

    app.run_polling()


if __name__ == "__main__":
    main()
