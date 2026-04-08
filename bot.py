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
    time TEXT,
    status TEXT DEFAULT 'pending'
)""")

# Migrate: add status column if upgrading from old database
try:
    c.execute("ALTER TABLE submissions ADD COLUMN status TEXT DEFAULT 'pending'")
    conn.commit()
except Exception:
    pass  # Column already exists

c.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    wallet TEXT,
    status TEXT
)""")

conn.commit()

# ── State tracking ──
pending_task = {}      # uid -> task_id
pending_withdraw = {}  # uid -> True
admin_state = {}       # uid -> state string
admin_temp = {}        # uid -> partial data dict

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
        "🛠 TaskHive Commands\n\n"
        "/start\n"
        "/tasks\n"
        "/points\n"
        "/profile\n"
        "/referral\n"
        "/withdraw\n\n"
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
    uid = update.effective_user.id
    c.execute("SELECT * FROM tasks")
    all_tasks = c.fetchall()

    if not all_tasks:
        await update.message.reply_text("No tasks available at the moment.")
        return

    keyboard = []
    for t in all_tasks:
        c.execute(
            "SELECT status FROM submissions WHERE user_id=? AND task_id=?",
            (uid, t[0]),
        )
        existing = c.fetchone()
        if existing:
            status = existing[0]
            if status == "approved":
                label = f"✅ {t[1]} (completed)"
            elif status == "pending":
                label = f"⏳ {t[1]} (under review)"
            else:
                label = f"❌ {t[1]} (rejected)"
        else:
            label = f"{t[1]} ({t[3]} pts)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"task_{t[0]}")])

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
# ADMIN PANEL
# ──────────────────────────────────────────────

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Task",        callback_data="admin_add")],
        [InlineKeyboardButton("✏️ Edit Task",       callback_data="admin_edit")],
        [InlineKeyboardButton("🗑 Delete Task",     callback_data="admin_delete")],
        [InlineKeyboardButton("👥 View Users",      callback_data="admin_users")],
        [InlineKeyboardButton("📋 Pending Reviews", callback_data="admin_pending")],
        [InlineKeyboardButton("📢 Broadcast",       callback_data="admin_broadcast")],
        [InlineKeyboardButton("📦 Download ZIP",    callback_data="admin_zip")],
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

        # Duplicate / status check
        c.execute(
            "SELECT status FROM submissions WHERE user_id=? AND task_id=?",
            (uid, task_id),
        )
        existing = c.fetchone()
        if existing:
            status = existing[0]
            if status == "approved":
                await query.message.reply_text("✅ You already completed this task and earned your points!")
            elif status == "pending":
                await query.message.reply_text("⏳ Your submission for this task is still under review. Please wait.")
            elif status == "rejected":
                await query.message.reply_text(
                    "❌ Your previous submission was rejected.\n\n"
                    "Please contact the admin if you think this was a mistake."
                )
            return

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

    # ── Admin-only from here ──
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
        await query.message.reply_text(
            "✏️ Which task do you want to edit?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("admin_edit_pick_"):
        task_id = int(data.split("_")[-1])
        c.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = c.fetchone()
        admin_temp[uid] = {"task_id": task_id}
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
        chunk_size = 50
        for i in range(0, len(lines), chunk_size):
            await query.message.reply_text(
                "\n".join(lines[i:i + chunk_size]),
                parse_mode="Markdown",
            )

    # ── Pending Submissions (Approval Queue) ──
    elif data == "admin_pending":
        c.execute("""
            SELECT s.id, u.username, u.id, t.title, s.file_path, s.text_answer, s.time
            FROM submissions s
            LEFT JOIN users u ON s.user_id = u.id
            LEFT JOIN tasks t ON s.task_id = t.id
            WHERE s.status = 'pending'
            ORDER BY s.time ASC
            LIMIT 10
        """)
        subs = c.fetchall()
        if not subs:
            await query.message.reply_text("✅ No pending submissions right now!")
            return
        for s in subs:
            sub_id, username, user_id, task_title, file_path, text_answer, sub_time = s
            uname = f"@{username}" if username and username != "user" else f"ID:{user_id}"
            caption = (
                f"📥 *Submission #{sub_id}*\n\n"
                f"👤 User: {uname}\n"
                f"📌 Task: {task_title}\n"
                f"🕐 Time: {sub_time}\n"
            )
            if text_answer:
                caption += f"💬 Answer: {text_answer}\n"
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{sub_id}"),
                    InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{sub_id}"),
                ]
            ])
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    if file_path.endswith(".jpg"):
                        await query.message.reply_photo(f, caption=caption, reply_markup=keyboard, parse_mode="Markdown")
                    elif file_path.endswith(".ogg"):
                        await query.message.reply_voice(f, caption=caption, reply_markup=keyboard, parse_mode="Markdown")
                    else:
                        await query.message.reply_document(f, caption=caption, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await query.message.reply_text(caption, reply_markup=keyboard, parse_mode="Markdown")

    # ── Approve submission ──
    elif data.startswith("approve_"):
        sub_id = int(data.split("_")[1])
        c.execute("SELECT user_id, task_id, status FROM submissions WHERE id=?", (sub_id,))
        sub = c.fetchone()
        if not sub:
            await query.message.reply_text("Submission not found.")
            return
        sub_user_id, task_id, current_status = sub
        if current_status != "pending":
            await query.message.reply_text("This submission was already reviewed.")
            return
        c.execute("SELECT points FROM tasks WHERE id=?", (task_id,))
        reward_row = c.fetchone()
        reward = reward_row[0] if reward_row else 0
        c.execute("UPDATE submissions SET status='approved' WHERE id=?", (sub_id,))
        c.execute("UPDATE users SET points = points + ? WHERE id=?", (reward, sub_user_id))
        conn.commit()
        await query.message.reply_text(f"✅ Approved! +{reward} pts sent to user.")
        try:
            await context.bot.send_message(
                sub_user_id,
                f"🎉 Your submission was *approved*!\n\n+{reward} points have been added to your account 💰",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    # ── Reject submission ──
    elif data.startswith("reject_"):
        sub_id = int(data.split("_")[1])
        c.execute("SELECT user_id, status FROM submissions WHERE id=?", (sub_id,))
        sub = c.fetchone()
        if not sub:
            await query.message.reply_text("Submission not found.")
            return
        sub_user_id, current_status = sub
        if current_status != "pending":
            await query.message.reply_text("This submission was already reviewed.")
            return
        c.execute("UPDATE submissions SET status='rejected' WHERE id=?", (sub_id,))
        conn.commit()
        await query.message.reply_text("❌ Submission rejected.")
        try:
            await context.bot.send_message(
                sub_user_id,
                "❌ Your submission was *rejected*.\n\nContact the admin if you think this was a mistake.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    # ── Broadcast ──
    elif data == "admin_broadcast":
        admin_state[uid] = "broadcast"
        await query.message.reply_text(
            "📢 Type your broadcast message and send it.\n\n"
            "Send /cancel to cancel."
        )

    # ── Download ZIP ──
    elif data == "admin_zip":
        zip_path = f"{DATA_DIR}/submissions_export.zip"
        try:
            with zipfile.ZipFile(zip_path, "w") as z:
                for fname in os.listdir(SUB_DIR):
                    z.write(os.path.join(SUB_DIR, fname), arcname=f"media/{fname}")
                c.execute("""
                    SELECT s.id, u.username, u.id, s.task_id, s.text_answer, s.file_path, s.time, s.status
                    FROM submissions s
                    LEFT JOIN users u ON s.user_id = u.id
                """)
                rows = c.fetchall()
                csv_lines = ["id,username,user_id,task_id,text_answer,file_path,time,status"]
                for r in rows:
                    csv_lines.append(",".join(str(x) if x is not None else "" for x in r))
                z.writestr("submissions.csv", "\n".join(csv_lines))
                c.execute("SELECT id, username, points, ref_by FROM users")
                urows = c.fetchall()
                ucsv = ["id,username,points,ref_by"]
                for r in urows:
                    ucsv.append(",".join(str(x) if x is not None else "" for x in r))
                z.writestr("users.csv", "\n".join(ucsv))
            with open(zip_path, "rb") as f:
                await query.message.reply_document(
                    f, filename="taskhive_export.zip", caption="📦 Full data export"
                )
        except Exception as e:
            await query.message.reply_text(f"❌ Error creating ZIP: {e}")


# ──────────────────────────────────────────────
# MESSAGE HANDLER
# ──────────────────────────────────────────────

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""

    # ── Admin conversation flows ──
    if uid == ADMIN_ID and uid in admin_state:
        state = admin_state[uid]

        # Broadcast
        if state == "broadcast":
            if text.strip() == "/cancel":
                admin_state.pop(uid, None)
                await update.message.reply_text("Broadcast cancelled.", reply_markup=admin_keyboard())
                return
            admin_state.pop(uid, None)
            c.execute("SELECT id FROM users")
            all_users = c.fetchall()
            sent = 0
            failed = 0
            await update.message.reply_text(f"📢 Sending to {len(all_users)} users...")
            for (user_id,) in all_users:
                try:
                    await context.bot.send_message(
                        user_id,
                        f"📢 *Announcement*\n\n{text}",
                        parse_mode="Markdown",
                    )
                    sent += 1
                except Exception:
                    failed += 1
            await update.message.reply_text(
                f"✅ Broadcast complete!\n\nSent: {sent}\nFailed: {failed}",
                reply_markup=admin_keyboard(),
            )
            return

        # Add task
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

        # Edit task
        elif state.startswith("edit_"):
            parts = state.split("_")
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
            await update.message.reply_text("✅ Task updated!", reply_markup=admin_keyboard())
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

        c.execute(
            "INSERT INTO submissions(user_id,task_id,file_path,text_answer,time,status) VALUES(?,?,?,?,?,?)",
            (
                uid,
                task_id,
                file_path,
                text if not file_path else None,
                str(datetime.now()),
                "pending",
            ),
        )
        conn.commit()

        # Notify admin
        c.execute("SELECT username FROM users WHERE id=?", (uid,))
        urow = c.fetchone()
        uname = f"@{urow[0]}" if urow and urow[0] and urow[0] != "user" else f"ID:{uid}"
        c.execute("SELECT title FROM tasks WHERE id=?", (task_id,))
        trow = c.fetchone()
        task_title = trow[0] if trow else "Unknown"
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"📥 *New submission pending review!*\n\n"
                f"👤 User: {uname}\n"
                f"📌 Task: {task_title}\n\n"
                f"Go to /admin → 📋 Pending Reviews",
                parse_mode="Markdown",
            )
        except Exception:
            pass

        await update.message.reply_text(
            "✅ Submission received!\n\n"
            "⏳ Your proof is under review. You'll be notified once it's approved."
        )
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
