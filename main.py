"""Telegram Reminder Bot — main entry point.

Commands:
    /start   — welcome message with quick-action buttons
    /new     — 4-step wizard to create a periodic reminder
    /list    — interactive reminder manager (inline delete buttons)
    /cancel  — abort the wizard at any step
"""

import logging
import os
from datetime import datetime, timedelta

import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# ConversationHandler states
ASK_MESSAGE, ASK_DATE, ASK_INTERVAL, ASK_TIME = range(4)

# Callback-data prefixes
CB_SHOW_LIST = "show_list"
CB_DELETE_PREFIX = "del_"

# ---------------------------------------------------------------------------
# Job callback
# ---------------------------------------------------------------------------


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fired by the JobQueue to deliver a reminder notification."""
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"🔔 *Reminder:* {job.data['message']}",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Scheduling helpers
# ---------------------------------------------------------------------------


def _compute_first_run(start_date: str, send_time: str, interval_days: int) -> datetime:
    """Return the next fire time (tz-aware, Israel time) for a reminder.

    When the original start_date/send_time is in the past the datetime is
    advanced by the minimum number of full intervals to land strictly in
    the future, preserving the original cadence.
    """
    hour, minute = map(int, send_time.split(":"))
    year, month, day = map(int, start_date.split("-"))

    # Use localize (not replace) so pytz applies the correct DST offset.
    first_run = ISRAEL_TZ.localize(datetime(year, month, day, hour, minute))
    now = datetime.now(ISRAEL_TZ)

    if first_run <= now:
        elapsed = (now - first_run).total_seconds()
        interval_secs = interval_days * 86_400
        intervals_passed = int(elapsed // interval_secs) + 1
        first_run += timedelta(seconds=intervals_passed * interval_secs)

    return first_run


def schedule_reminder(job_queue, reminder: dict) -> None:
    """Register a reminder dict as a repeating JobQueue job."""
    chat_id = reminder["chat_id"]
    reminder_id = reminder["id"]

    first_run = _compute_first_run(
        reminder["start_date"],
        reminder["send_time"],
        reminder["interval_days"],
    )

    job_queue.run_repeating(
        send_reminder,
        interval=timedelta(days=reminder["interval_days"]),
        first=first_run,
        name=f"reminder_{chat_id}_{reminder_id}",
        chat_id=chat_id,
        data={"message": reminder["message"], "reminder_id": reminder_id},
    )
    logger.info(
        "Scheduled reminder #%d for chat %d — next fire at %s",
        reminder_id,
        chat_id,
        first_run.isoformat(),
    )


def _cancel_job(job_queue, chat_id: int, reminder_id: int) -> None:
    """Remove the live job for a reminder from the JobQueue (if present)."""
    for job in job_queue.get_jobs_by_name(f"reminder_{chat_id}_{reminder_id}"):
        job.schedule_removal()


# ---------------------------------------------------------------------------
# Startup: rebuild JobQueue from PostgreSQL
# ---------------------------------------------------------------------------


def load_jobs_from_db(job_queue) -> None:
    """Bridge between persistence and scheduling.

    On every (re)start the in-memory JobQueue is empty.  This function
    reads the PostgreSQL reminders table and re-registers every row as a
    repeating job — called *after* Application.build() so the JobQueue
    object exists, and *before* run_polling() so the scheduler hasn't
    started yet.
    """
    reminders = database.get_all_reminders()
    loaded = 0
    for reminder in reminders:
        try:
            schedule_reminder(job_queue, reminder)
            loaded += 1
        except Exception:
            logger.exception("Could not reschedule reminder #%d — skipping", reminder["id"])
    logger.info("Reloaded %d / %d reminder(s) from PostgreSQL.", loaded, len(reminders))


# ---------------------------------------------------------------------------
# Shared UI helper — the management list
# ---------------------------------------------------------------------------


async def _send_reminder_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send one message per reminder, each with an inline Delete button.

    This is called by both the /list command and the 'Manage' callback so
    the rendering logic lives in exactly one place.
    """
    reminders = database.get_reminders_by_chat_id(chat_id)

    if not reminders:
        await context.bot.send_message(chat_id, "You have no active reminders.")
        return

    await context.bot.send_message(
        chat_id,
        f"📋 *Your reminders* ({len(reminders)} active):",
        parse_mode="Markdown",
    )

    for r in reminders:
        text = (
            f"🔔 *#{r['id']}* — {r['message']}\n"
            f"📅 Start: `{r['start_date']}` at `{r['send_time']}` (IL time)\n"
            f"🔄 Every: {r['interval_days']} day(s)"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"🗑 Delete #{r['id']}",
                callback_data=f"{CB_DELETE_PREFIX}{r['id']}",
            )
        ]])
        await context.bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Manage My Reminders", callback_data=CB_SHOW_LIST),
    ]])
    await update.message.reply_text(
        "👋 *Welcome to the Reminder Bot!*\n\n"
        "Commands:\n"
        "  /new     — Schedule a new reminder\n"
        "  /list    — Manage your active reminders\n"
        "  /cancel  — Abort the current wizard\n\n"
        "_All times are in Israel time (Asia/Jerusalem)._",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_reminder_list(update.effective_chat.id, context)


# ---------------------------------------------------------------------------
# Inline-keyboard callbacks
# ---------------------------------------------------------------------------


async def callback_show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'Manage My Reminders' button from /start."""
    query = update.callback_query
    await query.answer()
    await _send_reminder_list(query.message.chat_id, context)


async def callback_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a 'Delete #N' inline button press.

    Removes the reminder from PostgreSQL, cancels the live job, and edits
    the original message in-place so the button disappears immediately.
    """
    query = update.callback_query
    await query.answer()

    reminder_id = int(query.data.removeprefix(CB_DELETE_PREFIX))
    chat_id = query.message.chat_id

    deleted = database.delete_reminder(reminder_id, chat_id)

    if deleted:
        _cancel_job(context.job_queue, chat_id, reminder_id)
        await query.edit_message_text(f"🗑 Reminder #{reminder_id} has been deleted.")
        logger.info("Reminder #%d deleted by chat %d.", reminder_id, chat_id)
    else:
        # Already deleted (double-tap) or belongs to someone else
        await query.edit_message_text(f"⚠️ Reminder #{reminder_id} not found — it may already be deleted.")


# ---------------------------------------------------------------------------
# Conversation wizard — /new
# ---------------------------------------------------------------------------


async def conv_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Let's create a new reminder!\n\n"
        "Step 1 / 4 — What message should I send you?"
    )
    return ASK_MESSAGE


async def conv_received_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["message"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2 / 4 — Start date?\n"
        "Format: `YYYY-MM-DD`  (e.g. `2025-06-01`)",
        parse_mode="Markdown",
    )
    return ASK_DATE


async def conv_received_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_text = update.message.text.strip()
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "That doesn't look right. Please use the format `YYYY-MM-DD`:",
            parse_mode="Markdown",
        )
        return ASK_DATE

    context.user_data["start_date"] = date_text
    await update.message.reply_text(
        "Step 3 / 4 — Repeat interval?\n"
        "Enter the number of days between reminders (e.g. `3` for every 3 days):",
        parse_mode="Markdown",
    )
    return ASK_INTERVAL


async def conv_received_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        interval = int(update.message.text.strip())
        if interval < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a whole number greater than 0:")
        return ASK_INTERVAL

    context.user_data["interval_days"] = interval
    await update.message.reply_text(
        "Step 4 / 4 — At what time should I send it?\n"
        "Format: `HH:MM` in Israel time  (e.g. `09:00`)",
        parse_mode="Markdown",
    )
    return ASK_TIME


async def conv_received_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await update.message.reply_text(
            "That doesn't look right. Please use `HH:MM` format (e.g. `09:00`):",
            parse_mode="Markdown",
        )
        return ASK_TIME

    chat_id = update.effective_chat.id
    message = context.user_data["message"]
    start_date = context.user_data["start_date"]
    interval_days = context.user_data["interval_days"]

    reminder_id = database.add_reminder(chat_id, message, start_date, interval_days, time_text)

    reminder = {
        "id": reminder_id,
        "chat_id": chat_id,
        "message": message,
        "start_date": start_date,
        "interval_days": interval_days,
        "send_time": time_text,
    }
    schedule_reminder(context.job_queue, reminder)
    context.user_data.clear()

    await update.message.reply_text(
        f"✅ *Reminder #{reminder_id} saved!*\n\n"
        f"📝 Message : {message}\n"
        f"📅 Start   : `{start_date}` at `{time_text}` (IL time)\n"
        f"🔄 Repeat  : every {interval_days} day(s)\n\n"
        "Use /list to manage your reminders.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Cancelled. Use /new to start again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------


def main() -> None:
    database.init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # --- Conversation wizard ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("new", conv_start)],
        states={
            ASK_MESSAGE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_received_message)],
            ASK_DATE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_received_date)],
            ASK_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_received_interval)],
            ASK_TIME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, conv_received_time)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    )

    # --- Static commands ---
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("list", cmd_list))

    # --- Inline keyboard callbacks ---
    application.add_handler(CallbackQueryHandler(callback_show_list, pattern=f"^{CB_SHOW_LIST}$"))
    application.add_handler(CallbackQueryHandler(callback_delete, pattern=f"^{CB_DELETE_PREFIX}"))

    # --- Wizard (must come after plain commands so /cancel is caught correctly) ---
    application.add_handler(conv_handler)

    # Rebuild the JobQueue from PostgreSQL before the scheduler starts.
    load_jobs_from_db(application.job_queue)

    logger.info("Bot is running — press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
