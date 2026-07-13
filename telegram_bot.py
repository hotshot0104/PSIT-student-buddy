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
        ["📊 Attendance",  "📉 Miss Margin"],
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


async def _get_cached_data_or_scrape() -> dict:
    """Read the local cache, or trigger a scrape if missing/stale."""
    cache = erp.load_cache()
    is_today = False
    if cache and cache.get("student", {}).get("roll") == erp.ERP_USER:
        last_updated_str = cache.get("last_updated")
        if last_updated_str:
            try:
                last_updated = datetime.fromisoformat(last_updated_str).astimezone(IST)
                if last_updated.date() == datetime.now(tz=IST).date():
                    is_today = True
            except Exception:
                pass
        if is_today:
            return cache

    # Fallback: scrape once to initialize/refresh cache
    session, err = await asyncio.to_thread(erp.get_session)
    if not err:
        data = await asyncio.to_thread(erp.fetch_and_cache_all, session)
        if data:
            return data

    if cache and cache.get("student", {}).get("roll") == erp.ERP_USER:
        return cache
    return {}

def _clean_subject_str(subject_str: str) -> str:
    """Format '[ Name ][ Code ][ Room ][ G ]' to 'Name  Code  Room  G'."""
    if not subject_str:
        return ""
    return subject_str.replace("][", "  ").replace("[", "").replace("]", "").strip()


def _timetable_text(day_name, classes, offset: int):
    """Format a timetable response and build navigation inline keyboard."""
    if isinstance(classes, list) and classes:
        lines = []
        for c in classes:
            sub_cleaned = _clean_subject_str(c.get('subject'))
            lines.append(f"🕐 {c.get('time') or c.get('time_label')} — {sub_cleaned}")
        text  = f"📅 *Classes for {day_name}:*\n\n" + "\n".join(lines)
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
    """Format the attendance response (overall only, avoiding subject breakdown)."""
    if not isinstance(attendance, dict):
        return str(attendance)

    emoji = erp.attendance_emoji(attendance.get("overall", 0))
    text  = f"📊 *Overall Attendance:* {emoji} *{attendance['percent']}*"
    if attendance.get("present") is not None and attendance.get("total") is not None:
        text += f"\n({attendance['present']}/{attendance['total']} classes attended)"
    return text


def _miss_margin_text(attendance) -> str:
    """Format the miss margin response."""
    margin = erp.calc_miss_margin(attendance)
    if margin is None:
        return "⚠️ Couldn't calculate miss margin (missing present/total data)."

    emoji = erp.attendance_emoji(attendance.get("overall", 0))
    pct   = attendance.get("percent", "?")
    p, t  = margin["present"], margin["total"]

    if margin["can_miss"] > 0:
        return (
            f"📊 *Miss Margin*\n"
            f"Current: {emoji} {pct} ({p}/{t})\n\n"
            f"✅ You can miss *{margin['can_miss']} more class(es)* "
            f"and still stay above 75%."
        )
    return (
        f"📊 *Miss Margin*\n"
        f"Current: {emoji} {pct} ({p}/{t})\n\n"
        f"🚨 You *cannot miss any more classes!*\n"
        f"Attend *{margin['need_attend']} consecutive class(es)* to get back to 75%."
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
        "• 📉 Miss margin calculator\n"
        "• 🔮 Attendance Simulator (/simulate command)\n\n"
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
        "📉 Miss Margin":cmd_miss_margin,
        "🗓️ This Week": cmd_week,
        "⚙️ Settings":   cmd_settings,
        "❓ Help":        cmd_help,
        "📜 Logs":        cmd_logs,
    }
    fn = dispatch.get(update.message.text.strip())
    if fn:
        await fn(update, context)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching from cache...")
    data = await _get_cached_data_or_scrape()
    if not data:
        await msg.edit_text("⚠️ Could not load data from cache or ERP.")
        return
        
    day_name = datetime.now(tz=IST).strftime("%A")
    classes = data.get("today_classes", [])
    text, kb = _timetable_text(day_name, classes, 0)
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching from cache...")
    data = await _get_cached_data_or_scrape()
    if not data:
        await msg.edit_text("⚠️ Could not load data from cache or ERP.")
        return

    tomorrow_idx = (datetime.now(tz=IST).weekday() + 1) % 7
    tomorrow_name = erp.DAY_NAMES[tomorrow_idx]
    classes = data.get("timetable", {}).get(tomorrow_name, [])
    text, kb = _timetable_text(tomorrow_name, classes, 1)
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching attendance from cache...")
    data = await _get_cached_data_or_scrape()
    if not data:
        await msg.edit_text("⚠️ Could not load data from cache or ERP.")
        return
        
    text = _attendance_text(data.get("attendance", {}))
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📉 View Miss Margin", callback_data="miss_margin")
    ]])
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_miss_margin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Calculating miss margin...")
    data = await _get_cached_data_or_scrape()
    if not data:
        await msg.edit_text("⚠️ Could not load data from cache or ERP.")
        return
        
    await msg.edit_text(_miss_margin_text(data.get("attendance", {})), parse_mode="Markdown")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching weekly timetable...")
    data = await _get_cached_data_or_scrape()
    if not data:
        await msg.edit_text("⚠️ Could not load data from cache or ERP.")
        return

    week = data.get("timetable", {})
    today_idx = datetime.now(tz=IST).weekday()
    parts = ["🗓️ *This Week's Timetable:*\n"]

    for i, day_name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]):
        classes = week.get(day_name, [])
        marker = "📍 " if i == today_idx else ""
        if classes:
            lines = "\n".join(f"  • {c['time']} — {_clean_subject_str(c['subject'])}" for c in classes)
            parts.append(f"{marker}*{day_name}*\n{lines}")
        else:
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
        f"⏰ Morning briefing: *7:00 AM IST* (1 Login)\n"
        f"⚠️ Absent warning: *8:00 PM IST* (1 Login)\n"
        f"💾 Cache Mode: *Enabled* (All other commands load from local disk cache)\n\n"
        f"_Configure credentials dynamically in the web dashboard!_"
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
        "*📉 Miss Margin* — Classes you can skip / need to attend\n"
        "*🗓️ This Week* — Full weekly timetable\n"
        "*⚙️ Settings* — View current bot configuration\n"
        "*📜 Logs* — Today's reminder activity log\n"
        "*/simulate [sub] [att] [miss]* — Predict attendance change\n\n"
        "*🤖 Auto Features:*\n"
        "• Morning briefing at *7 AM* daily\n"
        "• Reminders *15 min* before each class starts\n"
        "• Absent alert at *8 PM* if you missed a lecture\n"
        "• *Timetable Swap alert* during morning briefing"
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


async def cmd_simulate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Predict attendance: /simulate [subject_fragment] [attended_count] [missed_count]
    Example: /simulate OS 5 2
    """
    if not is_authorized(update):
        return
        
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ *Usage:*\n`/simulate [subject_name] [to_attend] [to_miss]`\n\n"
            "*Example:* `/simulate OS 5 2` (predicts percentage if you attend 5 classes and miss 2 more)",
            parse_mode="Markdown"
        )
        return

    sub_query = args[0].lower()
    try:
        to_attend = int(args[1])
        to_skip = int(args[2])
    except ValueError:
        await update.message.reply_text("⚠️ Attended and skipped class counts must be numbers.")
        return

    data = await _get_cached_data_or_scrape()
    if not data:
        await update.message.reply_text("⚠️ Could not load attendance details.")
        return

    subjects = data.get("attendance", {}).get("subjects", [])
    target = None
    for s in subjects:
        if sub_query in s["name"].lower():
            target = s
            break

    if not target:
        sub_list = "\n".join(f"• `{s['name']}`" for s in subjects)
        await update.message.reply_text(
            f"⚠️ Subject matching `{args[0]}` not found.\n\n*Available subjects:*\n{sub_list}",
            parse_mode="Markdown"
        )
        return

    # Simulate
    p_curr = target["present"]
    t_curr = target["total"]
    
    p_new = p_curr + to_attend
    t_new = t_curr + to_attend + to_skip
    
    pct_new = (p_new / t_new * 100) if t_new > 0 else 0.0
    emoji = erp.attendance_emoji(pct_new)
    
    # Recalculate miss margin for simulated state
    sim_margin = erp.calc_miss_margin({"present": p_new, "total": t_new})
    
    reply = (
        f"🔮 *Simulated Attendance Predictor*\n"
        f"Subject: *{target['name']}*\n\n"
        f"📊 *Current Status:*\n"
        f"• {target['present']}/{target['total']} lectures ({target['percent']:.1f}%)\n\n"
        f"⚡ *Simulated Status (Attending {to_attend}, Missing {to_skip}):*\n"
        f"• *{p_new}/{t_new}* lectures attended\n"
        f"• New Percentage: {emoji} *{pct_new:.2f}%*\n\n"
    )
    
    if sim_margin:
        if sim_margin["can_miss"] > 0:
            reply += f"✅ You can miss *{sim_margin['can_miss']} more classes* after this."
        else:
            reply += f"🚨 You will need to attend *{sim_margin['need_attend']} consecutive classes* to recover back to 75%."
            
    await update.message.reply_text(reply, parse_mode="Markdown")


# ─────────────────────────────────────────
# INLINE KEYBOARD CALLBACK
# ─────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("day_"):
        offset = int(query.data.split("_")[1])
        data = await _get_cached_data_or_scrape()
        if not data:
            await query.edit_message_text("⚠️ Could not load timetable cache.")
            return
            
        target_idx = (datetime.now(tz=IST).weekday() + offset) % 7
        day_name = erp.DAY_NAMES[target_idx]
        classes = data.get("timetable", {}).get(day_name, [])
        text, kb = _timetable_text(day_name, classes, offset)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    elif query.data == "miss_margin":
        data = await _get_cached_data_or_scrape()
        if not data:
            await query.edit_message_text("⚠️ Could not load margin data.")
            return
        await query.edit_message_text(_miss_margin_text(data.get("attendance", {})), parse_mode="Markdown")


# ─────────────────────────────────────────
# SCHEDULED JOBS
# ─────────────────────────────────────────

async def job_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    """7:00 AM IST — Scrape ERP, rebuild cache, send daily summary + swap alerts."""
    global _morning_attendance_pct
    try:
        session, err = await asyncio.to_thread(erp.get_session)
        if err:
            await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"⚠️ Briefing login failed: {err}")
            return

        # Scrape and update the cache file
        data = await asyncio.to_thread(erp.fetch_and_cache_all, session)
        if not data:
            await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text="⚠️ Scheduled morning scrape failed.")
            return

        day_name = datetime.now(tz=IST).strftime("%A")
        classes = data.get("today_classes", [])
        attendance = data.get("attendance", {})

        # Cache morning attendance for evening comparison
        _morning_attendance_pct = attendance.get("overall", 0.0)

        # 1. Timetable Section
        if classes:
            lines = "\n".join(f"🕐 {c['time']} — {_clean_subject_str(c['subject'])}" for c in classes)
            tt_section = f"📅 *Classes for {day_name}:*\n{lines}"
        else:
            tt_section = f"🎉 *No classes today ({day_name})! Free day!*"

        # 2. Attendance Section
        emoji = erp.attendance_emoji(attendance.get("overall", 0))
        att_section = f"📊 *Overall Attendance:* {emoji} {attendance.get('percent', '0.0%')}"
        if attendance.get("present") is not None and attendance.get("total") is not None:
            att_section += f" ({attendance['present']}/{attendance['total']})"

        # 3. Swap Relocation Section (Feature 3)
        swap_section = ""
        relocations = data.get("relocations", [])
        if relocations:
            swap_section = "\n\n⚠️ *Timetable Changes/Relocations Detected:*\n"
            for r in relocations:
                orig_clean = _clean_subject_str(r['original'])
                new_clean = _clean_subject_str(r['new'])
                if r["type"] == "swap":
                    swap_section += f"• *{r['time']}*: {orig_clean} ➔ *{new_clean}*\n"
                else:
                    swap_section += f"• *{r['time']}*: Added *{new_clean}*\n"

        msg = (
            f"☀️ *Good morning, {erp.ERP_USER}!* (Cache updated)\n\n"
            f"{tt_section}\n\n"
            f"───────────────\n"
            f"{att_section}"
            f"{swap_section}\n\n"
            f"_— PSIT Student Buddy_"
        )
        await context.bot.send_message(chat_id=TELEGRAM_USER_ID, text=msg, parse_mode="Markdown")
        print(f"[{datetime.now(tz=IST).strftime('%H:%M')}] Morning briefing sent.")
    except Exception as e:
        print(f"[Morning Briefing Error] {e}")


async def job_class_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Every minute — Ping 15 minutes before each class using cache."""
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

        # Fetch timetable from cache (no login!)
        cache = erp.load_cache()
        if not cache:
            return

        classes = cache.get("today_classes", [])

        for cls in classes:
            time_str = cls.get("time") or cls.get("time_label")
            if not time_str:
                continue

            # Parse start time from the class time label string
            start_time = erp.parse_time(time_str)
            if start_time is None:
                continue

            key = f"{cls['subject']}_{start_time.strftime('%H:%M')}"
            if key in _reminders_sent:
                continue

            minutes_until = (start_time - now).total_seconds() / 60
            if 0 <= minutes_until <= 15:
                try:
                    sub_cleaned = _clean_subject_str(cls['subject'])
                    await context.bot.send_message(
                        chat_id=TELEGRAM_USER_ID,
                        text=(
                            f"🔔 *Class in ~15 minutes!*\n"
                            f"📚 *{sub_cleaned}* at *{time_str}*\n"
                            f"_Get ready! 🏃_"
                        ),
                        parse_mode="Markdown",
                    )
                    _reminders_sent.add(key)
                    log_msg = f"[{now.strftime('%H:%M')}] ✅ Sent: {sub_cleaned}"
                    _reminder_logs.append(log_msg)
                    print(log_msg)
                except Exception as e:
                    log_msg = f"[{now.strftime('%H:%M')}] ❌ Failed: {cls['subject']} ({e})"
                    _reminder_logs.append(log_msg)
    except Exception as e:
        print(f"[Reminder Loop Error] {e}")


async def job_absent_warning(context: ContextTypes.DEFAULT_TYPE):
    """8:00 PM IST — Scrape ERP to check for absences, compare vs morning percentage."""
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

        # Scrape and update the cache file
        data = await asyncio.to_thread(erp.fetch_and_cache_all, session)
        if not data:
            return

        # Strategy 1: Check daily record absence
        absent_subjects = data.get("absentToday", [])
        if absent_subjects:
            lines = "\n".join(f"❌ *{_clean_subject_str(sub)}*" for sub in absent_subjects)
            msg = (
                f"⚠️ *Absent Alert!*\n\n"
                f"You were marked *absent* in:\n\n{lines}\n\n"
                f"_Contact your faculty if this was a mistake._"
            )
            await context.bot.send_message(
                chat_id=TELEGRAM_USER_ID, text=msg, parse_mode="Markdown"
            )
            return

        # Strategy 2: Drop in percentage comparison
        attendance = data.get("attendance", {})
        curr_pct = attendance.get("overall", 0.0)

        if _morning_attendance_pct is not None:
            drop = _morning_attendance_pct - curr_pct
            if drop > 0.5:
                emoji = erp.attendance_emoji(curr_pct)
                msg = (
                    f"⚠️ *Attendance Drop Detected!*\n\n"
                    f"Morning: *{_morning_attendance_pct:.2f}%* -> Now: *{curr_pct:.2f}%*\n"
                    f"Current: {emoji} *{attendance.get('percent', '0.0%')}* "
                    f"({attendance.get('present', 0)}/{attendance.get('total', 0)})\n\n"
                    f"_It looks like you may have missed a class today._"
                )
            else:
                emoji = erp.attendance_emoji(curr_pct)
                msg = (
                    f"✅ *All good!* No attendance drop today!\n"
                    f"Current: {emoji} *{attendance.get('percent', '0.0%')}* "
                    f"({attendance.get('present', 0)}/{attendance.get('total', 0)})"
                )
        else:
            emoji = erp.attendance_emoji(curr_pct)
            msg = (
                f"📊 *Evening Attendance Summary*\n"
                f"Current: {emoji} *{attendance.get('percent', '0.0%')}* "
                f"({attendance.get('present', 0)}/{attendance.get('total', 0)})"
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
    app.add_handler(CommandHandler("simulate", cmd_simulate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Jobs — 7:00 AM IST (01:30 UTC)
    app.job_queue.run_daily(
        job_morning_briefing,
        time=dt_time(1, 30, tzinfo=timezone.utc),
    )
    # 8:00 PM IST (14:30 UTC)
    app.job_queue.run_daily(
        job_absent_warning,
        time=dt_time(14, 30, tzinfo=timezone.utc),
    )
    # Class pings check
    app.job_queue.run_repeating(job_class_reminder, interval=60, first=10)

    print("Bot started. Listening for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
