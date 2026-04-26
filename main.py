"""Telegram Reminder Bot — main entry point.

Commands available to users:
    /start   — show welcome message and usage
    /new     — start the 4-step wizard to schedule a reminder
    /list    — list your active reminders
    /delete  — delete a reminder by its ID
    /cancel  — abort the current wizard at any step
"""

import logging
import os
from datetime import datetime, timedelta

import pytz
from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
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

# ---------------------------------------------------------------------------
# Job callback
# ---------------------------------------------------------------------------


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fired by the JobQueue to deliver a reminder to the user."""
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"🔔 Reminder: {job.data['message']}",
    )


# ---------------------------------------------------------------------------
# Scheduling helper
# ---------------------------------------------------------------------------


def _compute_first_run(start_date: str, send_time: str, interval_days: int) -> datetime:
    """Return the next scheduled datetime (tz-aware, Israel time) for a reminder.

    If the original start_date/send_time is already in the past the function
    advances it by the minimum number of full intervals so that the returned
    datetime is strictly in the future.
    """
    hour, minute = map(int, send_time.split(":"))
    year, month, day = map(int, start_date.split("-"))

    # localize — not replace — so pytz handles DST correctly
    first_run = ISRAEL_TZ.localize(datetime(year, month, day, hour, minute))
    now = datetime.now(ISRAEL_TZ)

    if first_run <= now:
        elapsed_seconds = (now - first_run).total_seconds()
        interval_seconds = interval_days * 86_400
        intervals_passed = int(elapsed_seconds // interval_seconds) + 1
        first_run = first_run + timedelta(seconds=intervals_passed * interval_seconds)

    return first_run


def schedule_reminder(job_queue, reminder: dict) -> None:
    """Register a single reminder dict as a repeating JobQueue job."""
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


# ---------------------------------------------------------------------------
# Startup: reload persisted jobs
# ---------------------------------------------------------------------------


def load_jobs_from_db(job_queue) -> None:
    """Read every row from the database and register it with the JobQueue.

    This is the bridge between persistence and scheduling.  On a fresh start
    the in-memory JobQueue is empty; calling this function before
    ``run_polling`` brings it back in sync with the database so no reminder
    is silently lost across restarts.
    """
    reminders = database.get_all_reminders()
    loaded = 0
    for reminder in reminders:
        try:
            schedule_reminder(job_queue, reminder)
            loaded += 1
        except Exception:
            logger.exception("Could not reschedule reminder #%d — skipping", reminder["id"])
    logger.info("Loaded %d / %d reminder(s) from database.", loaded, len(reminders))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to the Reminder Bot!\n\n"
        "Commands:\n"
        "  /new     — Schedule a new reminder\n"
        "  /list    — List your active reminders\n"
        "  /delete  — Delete a reminder by ID\n"
        "  /cancel  — Abort the current wizard\n\n"
        "All times are in Israel time (Asia/Jerusalem)."
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reminders = database.get_reminders_by_chat_id(update.effective_chat.id)
    if not reminders:
        await update.message.reply_text("You have no active reminders.")
        return

    lines = ["Your reminders:\n"]
    for r in reminders:
        lines.append(
            f"🔔 #{r['id']} — {r['message']}\n"
            f"   Start : {r['start_date']} at {r['send_time']} (IL time)\n"
            f"   Repeat: every {r['interval_days']} day(s)\n"
        )
    await update.message.reply_text("\n".join(lines))


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: /delete <reminder_id>\n"
            "Run /list to see your reminder IDs."
        )
        return

    try:
        reminder_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a numeric reminder ID.")
        return

    chat_id = update.effective_chat.id
    deleted = database.delete_reminder(reminder_id, chat_id)

    if not deleted:
        await update.message.reply_text(
            f"Reminder #{reminder_id} not found or does not belong to you."
        )
        return

    # Remove the live job if it is still in the queue
    for job in context.job_queue.get_jobs_by_name(f"reminder_{chat_id}_{reminder_id}"):
        job.schedule_removal()

    await update.message.reply_text(f"Reminder #{reminder_id} deleted.")


# ---------------------------------------------------------------------------
# Conversation wizard — /new
# ---------------------------------------------------------------------------


async def conv_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: ask for the notification message."""
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
        "Format: YYYY-MM-DD  (e.g. 2025-06-01)"
    )
    return ASK_DATE


async def conv_received_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date_text = update.message.text.strip()
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "That doesn't look right. Please use the format YYYY-MM-DD:"
        )
        return ASK_DATE

    context.user_data["start_date"] = date_text
    await update.message.reply_text(
        "Step 3 / 4 — Repeat interval?\n"
        "Enter the number of days between reminders (e.g. 3 for every 3 days):"
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
        "Step 4 / 4 — At what time?\n"
        "Format: HH:MM in Israel time  (e.g. 09:00)"
    )
    return ASK_TIME


async def conv_received_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await update.message.reply_text(
            "That doesn't look right. Please use HH:MM format (e.g. 09:00):"
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
        f"✅ Reminder #{reminder_id} saved!\n\n"
        f"Message : {message}\n"
        f"Start   : {start_date} at {time_text} (IL time)\n"
        f"Repeat  : every {interval_days} day(s)"
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

    # 4-step conversation wizard
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

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("delete", cmd_delete))
    application.add_handler(conv_handler)

    # Re-register every reminder from the database before we start polling.
    # The JobQueue is available (but not yet running) at this point, so
    # run_repeating() calls succeed and the scheduler fires them on time.
    load_jobs_from_db(application.job_queue)

    logger.info("Bot is running — press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
