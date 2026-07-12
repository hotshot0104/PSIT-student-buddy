"""
telegram_bot.py — PSIT Student Buddy (Telegram)
Full-featured Telegram bot replacing the Discord bot.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta, time as dt_time

# Force UTF-8 output so emoji in log messages work on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from dotenv import load_dotenv

import erp

load_dotenv()

# ─────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_uid               = os.getenv("TELEGRAM_USER_ID", "0").strip()
TELEGRAM_USER_ID   = int(_uid) if _uid.isdigit() else 0

IST = timezone(timedelta(hours=5, minutes=30))

# ─────────────────────────────────────────
# PERSISTENT REPLY KEYBOARD
# ─────────────────────────────────────────
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📅 Today",       "📆 Tomorrow"],
        ["📊 Attendance",  "📉 Bunk Budget"],
        ["🗓️ This Week",  "⚙️ Settings"],
        ["❓ Help",        "📜 Logs"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ─────────────────────────────────────────
# STATE
# ─────────────────────────────────────────
_morning_attendance_pct = None   # Snapshot taken at 7 AM for 8 PM comparison
_reminders_sent: set    = set()
_reminders_date         = None
_reminder_logs: list    = []


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def is_authorized(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == TELEGRAM_USER_ID


def _timetable_text(day_name, classes, offset: int):
    """Format a timetable response and build navigation inline keyboard."""
    if isinstance(classes, list) and classes:
        lines = "\n".join(erp.format_classes(classes))
        text  = f"📅 *Classes for {day_name}:*\n\n{lines}"
    elif isinstance(classes, list):
        text = f"🎉 No classes on *{day_name}*! Free day!"
    else:
        text = str(classes)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀ Prev Day", callback_data=f"day_{offset - 1}"),
        InlineKeyboardButton("Next Day ▶", callback_data=f"day_{offset + 1}"),
    ]])
    return text, kb


def _attendance_text(attendance) -> str:
    """Format the attendance response (overall + subject-wise if available)."""
    if not isinstance(attendance, dict):
        return str(attendance)

    emoji = erp.attendance_emoji(attendance.get("percent_val", 0))
    text  = f"📊 *Overall Attendance:* {emoji} *{attendance['percent']}*"
    if attendance.get("present") is not None and attendance.get("total") is not None:
        text += f"\n({attendance['present']}/{attendance['total']} classes attended)"

    subjects = attendance.get("subjects", [])
    if subjects:
        text += "\n\n*📚 Subject-wise Breakdown:*"
        for s in subjects:
            se    = erp.attendance_emoji(s.get("percent", "0"))
            name  = (s.get("subject") or "Unknown")[:28]
            pct   = s.get("percent",  "N/A")
            pres  = s.get("present",  "?")
            tot   = s.get("total",    "?")
            text += f"\n{se} {name}: *{pct}* ({pres}/{tot})"
    return text


def _bunk_text(attendance) -> str:
    """Format the bunk budget response."""
    budget = erp.calc_bunk_budget(attendance)
    if budget is None:
        return "⚠️ Couldn't calculate bunk budget (missing present/total data)."

    emoji = erp.attendance_emoji(attendance.get("percent_val", 0))
    pct   = attendance.get("percent", "?")
    p, t  = budget["present"], budget["total"]

    if budget["can_bunk"] > 0:
        return (
            f"📊 *Bunk Budget*\n"
            f"Current: {emoji} {pct} ({p}/{t})\n\n"
            f"✅ You can skip *{budget['can_bunk']} more class(es)* "
            f"and still stay above 75%."
        )
    return (
        f"📊 *Bunk Budget*\n"
        f"Current: {emoji} {pct} ({p}/{t})\n\n"
        f"🚨 You *cannot bunk any more classes!*\n"
        f"Attend *{budget['need_attend']} consecutive class(es)* to get back to 75%."
    )


# ─────────────────────────────────────────
# COMMAND / MESSAGE HANDLERS
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "👋 *Welcome to PSIT Student Buddy!*\n\n"
        "I'm your personal academic assistant. I keep you on track with:\n"
        "• 📅 Daily timetable & attendance briefing at *7 AM*\n"
        "• 🔔 Class reminders *15 minutes* before each lecture\n"
        "• ⚠️ Absent alert at *8 PM* if you missed a class\n"
        "• 📉 Bunk budget calculator\n\n"
        "Use the menu below to get started! 🎓",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    dispatch = {
        "📅 Today":      cmd_today,
        "📆 Tomorrow":   cmd_tomorrow,
        "📊 Attendance": cmd_attendance,
        "📉 Bunk Budget":cmd_bunk,
        "🗓️ This Week": cmd_week,
        "⚙️ Settings":   cmd_settings,
        "❓ Help":        cmd_help,
        "📜 Logs":        cmd_logs,
    }
    fn = dispatch.get(update.message.text.strip())
    if fn:
        await fn(update, context)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching from ERP...")
    session, err = await asyncio.to_thread(erp.get_session)
    if err:
        await msg.edit_text(err)
        return
    day_name, classes = await asyncio.to_thread(erp.get_today_classes, session)
    text, kb = _timetable_text(day_name, classes, 0)
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching from ERP...")
    session, err = await asyncio.to_thread(erp.get_session)
    if err:
        await msg.edit_text(err)
        return
    day_name, classes = await asyncio.to_thread(erp.get_classes_for_day, session, 1)
    text, kb = _timetable_text(day_name, classes, 1)
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching attendance from ERP...")
    session, err = await asyncio.to_thread(erp.get_session)
    if err:
        await msg.edit_text(err)
        return
    attendance = await asyncio.to_thread(erp.get_attendance, session)
    text       = _attendance_text(attendance)
    kb         = InlineKeyboardMarkup([[
        InlineKeyboardButton("📉 View Bunk Budget", callback_data="bunk")
    ]])
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_bunk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Calculating bunk budget...")
    session, err = await asyncio.to_thread(erp.get_session)
    if err:
        await msg.edit_text(err)
        return
    attendance = await asyncio.to_thread(erp.get_attendance, session)
    await msg.edit_text(_bunk_text(attendance), parse_mode="Markdown")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching full week timetable...")
    session, err = await asyncio.to_thread(erp.get_session)
    if err:
        await msg.edit_text(err)
        return
    week      = await asyncio.to_thread(erp.get_week_timetable, session)
    today_idx = datetime.now(tz=IST).weekday()
    parts     = ["🗓️ *This Week's Timetable:*\n"]

    for i, (day_name, classes) in enumerate(week):
        marker = "📍 " if i == today_idx else ""
        if isinstance(classes, list) and classes:
            lines = "\n".join(f"  • {c['time_label']} — {c['subject']}" for c in classes)
            parts.append(f"{marker}*{day_name}*\n{lines}")
        elif isinstance(classes, list):
            parts.append(f"{marker}*{day_name}* — 🎉 No classes")

    reply = "\n\n".join(parts)
    if len(reply) > 4000:
        reply = reply[:4000] + "\n\n_...truncated_"
    await msg.edit_text(reply, parse_mode="Markdown")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    reply = (
        "⚙️ *Settings*\n\n"
        f"ERP User: {'✅ Set' if erp.ERP_USER else '❌ Not set'}\n"
        f"ERP Password: {'✅ Set' if erp.ERP_PASSWORD else '❌ Not set'}\n\n"
        f"⏰ Morning briefing: *7:00 AM IST*\n"
        f"🔔 Class reminder: *15 min before each class*\n"
        f"⚠️ Absent warning: *8:00 PM IST*\n\n"
        f"_To change credentials, edit `.env` and restart the bot._"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    reply = (
        "❓ *PSIT Student Buddy — Help*\n\n"
        "*📅 Today* — Today's class schedule\n"
        "*📆 Tomorrow* — Tomorrow's classes\n"
        "*📊 Attendance* — Overall & subject-wise attendance\n"
        "*📉 Bunk Budget* — Classes you can skip / need to attend\n"
        "*🗓️ This Week* — Full weekly timetable\n"
        "*⚙️ Settings* — View current bot configuration\n"
        "*📜 Logs* — Today's reminder activity log\n\n"
        "*🤖 Auto Features:*\n"
        "• Morning briefing at *7 AM* daily\n"
        "• Reminders *15 min* before each class starts\n"
        "• Absent alert at *8 PM* if you missed a lecture"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not _reminder_logs:
        await update.message.reply_text("📭 No reminder logs for today yet.", parse_mode="Markdown")
    else:
        logs_text = "\n".join(_reminder_logs[-15:])
        await update.message.reply_text(
            f"📜 *Today's Reminder Logs:*\n{logs_text}",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────
# INLINE KEYBOARD CALLBACK
# ─────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("day_"):
        offset = int(query.data.split("_")[1])
        session, err = await asyncio.to_thread(erp.get_session)
        if err:
            await query.edit_message_text(err)
            return
        day_name, classes = await asyncio.to_thread(erp.get_classes_for_day, session, offset)
        text, kb = _timetable_text(day_name, classes, offset)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    elif query.data == "bunk":
        session, err = await asyncio.to_thread(erp.get_session)
        if err:
            await query.edit_message_text(err)
            return
        attendance = await asyncio.to_thread(erp.get_attendance, session)
        await query.edit_message_text(_bunk_text(attendance), parse_mode="Markdown")


# ─────────────────────────────────────────
# SCHEDULED JOBS
# ─────────────────────────────────────────

async def job_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    """7:00 AM IST — Send timetable + attendance summary and snapshot attendance %."""
    global _morning_attendance_pct
    try:
        session, err = await asyncio.to_thread(erp.get_session)
        if err:
            await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text=err)
            return

        day_name, classes = await asyncio.to_thread(erp.get_today_classes, session)
        attendance        = await asyncio.to_thread(erp.get_attendance, session)

        # Cache morning attendance for the 8 PM absent-warning comparison
        if isinstance(attendance, dict):
            _morning_attendance_pct = attendance.get("percent_val")

        if isinstance(classes, list) and classes:
            lines      = "\n".join(erp.format_classes(classes))
            tt_section = f"📅 *Classes for {day_name}:*\n{lines}"
        elif isinstance(classes, list):
            tt_section = f"🎉 *No classes today ({day_name})! Free day!*"
        else:
            tt_section = str(classes)

        if isinstance(attendance, dict):
            emoji       = erp.attendance_emoji(attendance["percent_val"])
            att_section = f"📊 *Overall Attendance:* {emoji} {attendance['percent']}"
            if attendance["present"] is not None and attendance["total"] is not None:
                att_section += f" ({attendance['present']}/{attendance['total']})"
        else:
            att_section = str(attendance)

        msg = (
            f"☀️ *Good morning, {erp.ERP_USER}!*\n\n"
            f"{tt_section}\n\n"
            f"───────────────\n"
            f"{att_section}\n\n"
            f"_— PSIT Student Buddy_"
        )
        await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text=msg, parse_mode="Markdown")
        print(f"[{datetime.now(tz=IST).strftime('%H:%M')}] Morning briefing sent.")
    except Exception as e:
        print(f"[Morning Briefing Error] {e}")


async def job_class_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Every minute — Ping the user 15 minutes before each class."""
    global _reminders_sent, _reminders_date, _reminder_logs
    try:
        now   = datetime.now(tz=IST)
        today = now.date()

        # Reset daily state at midnight
        if _reminders_date != today:
            _reminders_sent = set()
            _reminder_logs  = []
            _reminders_date = today

        # Only run during class hours
        if not (6 <= now.hour < 20):
            return

        session, err = await asyncio.to_thread(erp.get_session)
        if err:
            return

        classes = await asyncio.to_thread(erp.get_cached_today_classes, session)
        if not isinstance(classes, list):
            return

        for cls in classes:
            start_time = cls["start_time"]
            if start_time is None:
                continue

            key = f"{cls['subject']}_{start_time.strftime('%H:%M')}"
            if key in _reminders_sent:
                continue

            minutes_until = (start_time - now).total_seconds() / 60
            if 0 <= minutes_until <= 15:
                try:
                    await context.bot.send_message(
                        chat_id=TELEGRAM_USER_ID,
                        text=(
                            f"🔔 *Class in ~15 minutes!*\n"
                            f"📚 *{cls['subject']}* at *{cls['time_label']}*\n"
                            f"_Get ready! 🏃_"
                        ),
                        parse_mode="Markdown",
                    )
                    _reminders_sent.add(key)
                    log_msg = f"[{now.strftime('%H:%M')}] ✅ Sent: {cls['subject']}"
                    _reminder_logs.append(log_msg)
                    print(log_msg)
                except Exception as e:
                    log_msg = f"[{now.strftime('%H:%M')}] ❌ Failed: {cls['subject']} ({e})"
                    _reminder_logs.append(log_msg)
    except Exception as e:
        print(f"[Reminder Loop Error] {e}")


async def job_absent_warning(context: ContextTypes.DEFAULT_TYPE):
    """
    8:00 PM IST — Check if the student was marked absent in any class today.
    """
    global _morning_attendance_pct
    try:
        now = datetime.now(tz=IST)
        if now.weekday() >= 5:  # Skip Saturday & Sunday
            return

        session, err = await asyncio.to_thread(erp.get_session)
        if err:
            await context.bot.send_message(
                chat_id=TELEGRAM_USER_ID,
                text=f"⚠️ Evening attendance check failed: {err}",
            )
            return

        daily_records = await asyncio.to_thread(erp.get_daily_attendance, session)
        if daily_records is not None:
            absent = [r for r in daily_records if "absent" in r.get("status", "").lower()]
            if absent:
                lines = "\n".join(
                    f"❌ *{r['subject']}*" + (f" ({r['time']})" if r.get("time") else "")
                    for r in absent
                )
                msg = (
                    f"⚠️ *Absent Alert!*\n\n"
                    f"You were marked *absent* in:\n\n{lines}\n\n"
                    f"_Contact your faculty if this was a mistake._"
                )
            else:
                msg = "✅ *Great job!* You attended all classes today! 🎉"
            await context.bot.send_message(
                chat_id=TELEGRAM_USER_ID, text=msg, parse_mode="Markdown"
            )
            return

        # Fallback to overall % check
        current = await asyncio.to_thread(erp.get_attendance, session)
        if not isinstance(current, dict):
            return

        curr_pct = current.get("percent_val", 0)

        if _morning_attendance_pct is not None:
            drop = _morning_attendance_pct - curr_pct
            if drop > 0.5:
                emoji = erp.attendance_emoji(curr_pct)
                msg = (
                    f"⚠️ *Attendance Drop Detected!*\n\n"
                    f"Morning: *{_morning_attendance_pct:.2f}%* -> Now: *{curr_pct:.2f}%*\n"
                    f"Current: {emoji} *{current['percent']}* "
                    f"({current['present']}/{current['total']})\n\n"
                    f"_It looks like you may have missed a class today._"
                )
            else:
                emoji = erp.attendance_emoji(curr_pct)
                msg = (
                    f"✅ *All good!* No attendance drop today!\n"
                    f"Current: {emoji} *{current['percent']}* "
                    f"({current['present']}/{current['total']})"
                )
        else:
            emoji = erp.attendance_emoji(curr_pct)
            msg = (
                f"📊 *Evening Attendance Summary*\n"
                f"Current: {emoji} *{current['percent']}* "
                f"({current['present']}/{current['total']})"
            )

        await context.bot.send_message(
            chat_id=TELEGRAM_USER_ID, text=msg, parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[Absent Warning Error] {e}")


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env file! Get one from @BotFather on Telegram.")
        return
    if not TELEGRAM_USER_ID:
        print("❌ TELEGRAM_USER_ID not set in .env file!")
        return

    print("--- STARTUP ---")
    print(f"ERP_USER:     {'OK' if erp.ERP_USER     else 'NOT SET'}")
    print(f"ERP_PASSWORD: {'OK' if erp.ERP_PASSWORD else 'NOT SET'}")
    print(f"BOT_TOKEN:    OK (length: {len(TELEGRAM_BOT_TOKEN)})")
    print(f"USER_ID:      {TELEGRAM_USER_ID}")
    print("---------------")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logs",  cmd_logs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Jobs
    app.job_queue.run_daily(
        job_morning_briefing,
        time=dt_time(1, 30, tzinfo=timezone.utc),
    )
    app.job_queue.run_daily(
        job_absent_warning,
        time=dt_time(14, 30, tzinfo=timezone.utc),
    )
    app.job_queue.run_repeating(job_class_reminder, interval=60, first=10)

    print("Bot started. Listening for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
