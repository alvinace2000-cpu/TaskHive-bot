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
    filters,
)

TOKEN = os.getenv("TOKEN")

BOT_USERNAME = "Task_Hive"
ADMIN_ID = 8728887265
CHANNEL_LINK = "https://t.me/+6WtlEwqjwccxOTVk"

DATA_DIR = "data"
SUB_DIR = f"{DATA_DIR}/submissions"

os.makedirs(SUB_DIR, exist_ok=True)

conn = sqlite3.connect(f"{DATA_DIR}/taskhive.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0,
    ref_by INTEGER
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
    file_path TEXT,
    text_answer TEXT,
    time TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    wallet TEXT,
    status TEXT
)""")

conn.commit()

# --- State tracking dicts ---
pending_task = {}       # uid -> task_id  (user is submitting proof)
pending_withdraw = {}   # uid -> True      (user is entering wallet)

# Admin conversation states
# Values: "add_title", "add_desc", "add_pts",
#         "edit_pick", "edit_field_{task_id}", "edit_title_{task_id}", "edit_desc_{task_id}", "edit_pts_{task_id}",
#         "delete_pick"
admin_state = {}
admin_temp = {}         # uid -> partial data dict during add/edit flows

MIN_WITHDRAW = 1500


# ──────────────────────────────────────────────
# USER COMMANDS
# ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or "user"

    ref = None
    if context.args and "ref_" in context.args[0]:
        try:
            ref = int(context.args[0].split("_")[1])
        except ValueError:
            pass

    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    result = c.fetchone()

    if result:
        pts = result[2]
        await update.message.reply_text(
            f"👋 Welcome back @{username}\n\n"
            f"💰 Your Points: {pts}\n\n"
            f"Use /tasks to start earning more points."
        )
    else:
        c.execute(
            "INSERT INTO users(id,username,points,ref_by) VALUES(?,?,?,?)",
            (user_id, username, 50, ref),
        )
        conn.commit()

        if ref and ref != user_id:
            c.execute("UPDATE users SET points = points + 150 WHERE id=?", (ref,))
            conn.commit()

        await update.message.reply_text(
            f"👋 Welcome to TaskHive @{username}\n\n"
            f"You received 🎁 50 bonus points!\n\n"
            f"Complete tasks and earn rewards.\n\n"
            f"Join announcements👇\n{CHANNEL_LINK}\n\n"
            f"Use /tasks to start."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🛠 TaskHive Commands\n\n"
        f"/start\n"
        f"/tasks\n"
        f"/points\n"
        f"/profile\n"
        f"/referral\n"
        f"/withdraw\n\n"
        f"Join announcements👇\n{CHANNEL_LINK}"
    )


async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT points FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("You're not registered yet. Use /start first.")
        return
    await update.message.reply_text(
        f"💰 Your current points: *{row[0]}*\n\n"
        f"Keep completing tasks to earn more!",
        parse_mode="Markdown",
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT points FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("You're not registered yet. Use /start first.")
        return
    await update.message.reply_text(
        f"👤 Profile\n\n"
        f"💰 Points: {row[0]}\n\n"
        f"Minimum withdrawal: {MIN_WITHDRAW}"
    )


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🔗 Your referral link\n\n"
        f"https://t.me/{BOT_USERNAME}?start=ref_{uid}\n\n"
        f"Earn 150 points per referral"
    )


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c.execute("SELECT * FROM tasks")
    all_tasks = c.fetchall()

    if not all_tasks:
        await update.message.reply_text("No tasks available at the moment.")
        return

    keyboard = [
        [InlineKeyboardButton(f"{t[1]} ({t[3]} pts)", callback_data=f"task_{t[0]}")]
        for t in all_tasks
    ]
    await update.message.reply_text(
        "📋 Available Tasks — tap one to start:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    c.execute("SELECT points FROM users WHERE id=?", (uid,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("Use /start first.")
        return
    pts = row[0]
    if pts < MIN_WITHDRAW:
        await update.message.reply_text(
            f"❌ You need at least {MIN_WITHDRAW} points to withdraw.\n"
            f"You currently have {pts} points."
        )
        return
    pending_withdraw[uid] = True
    await update.message.reply_text("💳 Please send your crypto wallet address:")


# ──────────────────────────────────────────────
# ADMIN COMMAND & PANEL
# ──────────────────────────────────────────────

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task",    callback_data="admin_add")],
        [InlineKeyboardButton("✏️ Edit Task",   callback_data="admin_edit")],
        [InlineKeyboardButton("🗑 Delete Task", callback_data="admin_delete")],
        [InlineKeyboardButton("👥 View Users",  callback_data="admin_users")],
        [InlineKeyboardButton("📦 Download ZIP", callback_data="admin_zip")],
    ])


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🔧 Admin Panel", reply_markup=admin_keyboard())


# ──────────────────────────────────────────────
# CALLBACK ROUTER
# ──────────────────────────────────────────────

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    # ── User: select a task ──
    if data.startswith("task_"):
        task_id = int(data.split("_")[1])
        c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = c.fetchone()
        if not task:
            await query.message.reply_text("❌ Task not found.")
            return
        pending_task[uid] = task_id
        await query.message.reply_text(
            f"✅ Task Selected\n\n"
            f"📌 {task[1]}\n\n"
            f"{task[2]}\n\n"
            f"Send your proof now (photo, voice note, or text)."
        )
        return

    # ── Admin-only callbacks ──
    if uid != ADMIN_ID:
        return

    if data == "admin_panel":
        await query.message.reply_text("🔧 Admin Panel", reply_markup=admin_keyboard())

    # ── Add Task ──
    elif data == "admin_add":
        admin_state[uid] = "add_title"
        admin_temp[uid] = {}
        await query.message.reply_text("📝 Enter the *task title*:", parse_mode="Markdown")

    # ── Edit Task ──
    elif data == "admin_edit":
        c.execute("SELECT id, title FROM tasks")
        all_tasks = c.fetchall()
        if not all_tasks:
            await query.message.reply_text("No tasks to edit.")
            return
        keyboard = [
            [InlineKeyboardButton(t[1], callback_data=f"admin_edit_pick_{t[0]}")]
            for t in all_tasks
        ]
        keyboard.append([InlineKeyboardButton("« Back", callback_data="admin_panel")])
        admin_state[uid] = "edit_pick"
        await query.message.reply_text(
            "✏️ Which task do you want to edit?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("admin_edit_pick_"):
        task_id = int(data.split("_")[-1])
        c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = c.fetchone()
        admin_temp[uid] = {"task_id": task_id, "task": task}
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Title",       callback_data=f"admin_edit_field_title_{task_id}")],
            [InlineKeyboardButton("Description", callback_data=f"admin_edit_field_desc_{task_id}")],
            [InlineKeyboardButton("Points",      callback_data=f"admin_edit_field_pts_{task_id}")],
            [InlineKeyboardButton("« Back",      callback_data="admin_edit")],
        ])
        await query.message.reply_text(
            f"Editing: *{task[1]}*\n\nWhat do you want to change?",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif data.startswith("admin_edit_field_"):
        parts = data.split("_")
        # format: admin_edit_field_{title|desc|pts}_{task_id}
        field = parts[3]
        task_id = int(parts[4])
        admin_state[uid] = f"edit_{field}_{task_id}"
        prompts = {
            "title": "Enter the new *title*:",
            "desc":  "Enter the new *description*:",
            "pts":   "Enter the new *points* value (number):",
        }
        await query.message.reply_text(prompts[field], parse_mode="Markdown")

    # ── Delete Task ──
    elif data == "admin_delete":
        c.execute("SELECT id, title FROM tasks")
        all_tasks = c.fetchall()
        if not all_tasks:
            await query.message.reply_text("No tasks to delete.")
            return
        keyboard = [
            [InlineKeyboardButton(f"🗑 {t[1]}", callback_data=f"admin_delete_confirm_{t[0]}")]
            for t in all_tasks
        ]
        keyboard.append([InlineKeyboardButton("« Back", callback_data="admin_panel")])
        await query.message.reply_text(
            "🗑 Select a task to delete:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("admin_delete_confirm_"):
        task_id = int(data.split("_")[-1])
        c.execute("SELECT title FROM tasks WHERE id=?", (task_id,))
        row = c.fetchone()
        if not row:
            await query.message.reply_text("Task not found.")
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, delete", callback_data=f"admin_delete_do_{task_id}")],
            [InlineKeyboardButton("❌ Cancel",       callback_data="admin_delete")],
        ])
        await query.message.reply_text(
            f"Are you sure you want to delete *{row[0]}*?",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif data.startswith("admin_delete_do_"):
        task_id = int(data.split("_")[-1])
        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
        await query.message.reply_text("🗑 Task deleted.", reply_markup=admin_keyboard())

    # ── View Users ──
    elif data == "admin_users":
        c.execute("SELECT id, username, points FROM users ORDER BY points DESC")
        users = c.fetchall()
        if not users:
            await query.message.reply_text("No users yet.")
            return
        total = len(users)
        lines = [f"👥 *Total users: {total}*\n"]
        for u in users:
            uname = f"@{u[1]}" if u[1] and u[1] != "user" else f"ID:{u[0]}"
            lines.append(f"• {uname} — {u[2]} pts")
        # Telegram message limit: send in chunks of 50 users
        chunk_size = 50
        for i in range(0, len(lines), chunk_size):
            await query.message.reply_text(
                "\n".join(lines[i:i + chunk_size]),
                parse_mode="Markdown",
            )

    # ── Download ZIP ──
    elif data == "admin_zip":
        zip_path = f"{DATA_DIR}/submissions_export.zip"
        try:
            with zipfile.ZipFile(zip_path, "w") as z:
                # Include all submission media files
                for fname in os.listdir(SUB_DIR):
                    z.write(os.path.join(SUB_DIR, fname), arcname=f"media/{fname}")
                # Include a CSV export of the submissions table
                c.execute("""
                    SELECT s.id, u.username, u.id, s.task_id, s.text_answer, s.file_path, s.time
                    FROM submissions s
                    LEFT JOIN users u ON s.user_id = u.id
                """)
                rows = c.fetchall()
                csv_lines = ["id,username,user_id,task_id,text_answer,file_path,time"]
                for r in rows:
                    csv_lines.append(",".join(str(x) if x else "" for x in r))
                z.writestr("submissions.csv", "\n".join(csv_lines))

                # Include users CSV
                c.execute("SELECT id, username, points, ref_by FROM users")
                urows = c.fetchall()
                ucsv = ["id,username,points,ref_by"]
                for r in urows:
                    ucsv.append(",".join(str(x) if x else "" for x in r))
                z.writestr("users.csv", "\n".join(ucsv))

            with open(zip_path, "rb") as f:
                await query.message.reply_document(
                    f, filename="taskhive_export.zip", caption="📦 Full data export"
                )
        except Exception as e:
            await query.message.reply_text(f"❌ Error creating ZIP: {e}")


# ──────────────────────────────────────────────
# MESSAGE HANDLER  (plain text + media)
# ──────────────────────────────────────────────

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""

    # ── Admin conversation flows ──
    if uid == ADMIN_ID and uid in admin_state:
        state = admin_state[uid]

        # Add task flow
        if state == "add_title":
            admin_temp[uid]["title"] = text
            admin_state[uid] = "add_desc"
            await update.message.reply_text("📝 Enter the *task description*:", parse_mode="Markdown")
            return

        elif state == "add_desc":
            admin_temp[uid]["desc"] = text
            admin_state[uid] = "add_pts"
            await update.message.reply_text("💰 Enter the *points* reward (number):", parse_mode="Markdown")
            return

        elif state == "add_pts":
            try:
                pts = int(text)
            except ValueError:
                await update.message.reply_text("❌ Please enter a valid number.")
                return
            d = admin_temp.pop(uid)
            admin_state.pop(uid)
            c.execute(
                "INSERT INTO tasks(title,description,points) VALUES(?,?,?)",
                (d["title"], d["desc"], pts),
            )
            conn.commit()
            await update.message.reply_text(
                f"✅ Task *{d['title']}* added with {pts} pts!",
                parse_mode="Markdown",
                reply_markup=admin_keyboard(),
            )
            return

        # Edit task flow
        elif state.startswith("edit_"):
            parts = state.split("_")  # edit_{field}_{task_id}
            field = parts[1]
            task_id = int(parts[2])

            if field == "title":
                c.execute("UPDATE tasks SET title=? WHERE id=?", (text, task_id))
            elif field == "desc":
                c.execute("UPDATE tasks SET description=? WHERE id=?", (text, task_id))
            elif field == "pts":
                try:
                    pts = int(text)
                except ValueError:
                    await update.message.reply_text("❌ Please enter a valid number.")
                    return
                c.execute("UPDATE tasks SET points=? WHERE id=?", (pts, task_id))

            conn.commit()
            admin_state.pop(uid, None)
            admin_temp.pop(uid, None)
            await update.message.reply_text(
                "✅ Task updated!",
                reply_markup=admin_keyboard(),
            )
            return

    # ── Withdraw wallet entry ──
    if uid in pending_withdraw and update.message.text:
        wallet = update.message.text
        c.execute("SELECT points FROM users WHERE id=?", (uid,))
        row = c.fetchone()
        if row and row[0] >= MIN_WITHDRAW:
            c.execute(
                "INSERT INTO withdrawals(user_id,amount,wallet,status) VALUES(?,?,?,?)",
                (uid, MIN_WITHDRAW, wallet, "pending"),
            )
            c.execute(
                "UPDATE users SET points = points - ? WHERE id=?",
                (MIN_WITHDRAW, uid),
            )
            conn.commit()
        pending_withdraw.pop(uid, None)
        await update.message.reply_text("✅ Withdrawal request submitted!")
        return

    # ── Task submission (proof) ──
    if uid in pending_task:
        task_id = pending_task.pop(uid)
        file_path = None

        if update.message.photo:
            file = await update.message.photo[-1].get_file()
            file_path = f"{SUB_DIR}/{uid}_{datetime.now().timestamp()}.jpg"
            await file.download_to_drive(file_path)
        elif update.message.voice:
            file = await update.message.voice.get_file()
            file_path = f"{SUB_DIR}/{uid}_{datetime.now().timestamp()}.ogg"
            await file.download_to_drive(file_path)
        # else: text submission (file_path stays None, text saved below)

        c.execute(
            "INSERT INTO submissions(user_id,task_id,file_path,text_answer,time) VALUES(?,?,?,?,?)",
            (uid, task_id, file_path, text if not file_path else None, str(datetime.now())),
        )

        c.execute("SELECT points FROM tasks WHERE id=?", (task_id,))
        reward_row = c.fetchone()
        reward = reward_row[0] if reward_row else 0

        c.execute("UPDATE users SET points = points + ? WHERE id=?", (reward, uid))
        conn.commit()

        await update.message.reply_text(f"✅ Submission received! +{reward} points 🎉")
        return


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("help",     help_command))
    app.add_handler(CommandHandler("tasks",    tasks))
    app.add_handler(CommandHandler("points",   points))
    app.add_handler(CommandHandler("profile",  profile))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("admin",    admin))

    app.add_handler(CallbackQueryHandler(button))

    # Single message handler covers text, photos, and voice notes
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.VOICE,
            message_handler,
        )
    )

    print("TaskHive Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
