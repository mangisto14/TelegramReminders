"""Telegram Reminder Bot — main entry point.

Commands:
    /start      — welcome screen (asks language on first visit)
    /new        — 4-step wizard to create a periodic reminder
    /list       — interactive reminder manager with inline delete buttons
    /language   — change your language preference at any time
    /cancel     — abort the current wizard
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
from strings import t

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
BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]

# ConversationHandler states
ASK_MESSAGE, ASK_DATE, ASK_INTERVAL, ASK_TIME = range(4)

# Callback-data constants
CB_SHOW_LIST      = "show_list"
CB_LANG_PREFIX    = "lang_"
CB_DELETE_PREFIX  = "del_"

# ---------------------------------------------------------------------------
# Localisation helpers
# ---------------------------------------------------------------------------


def _get_lang(chat_id: int) -> str:
    """Return the user's saved language code, defaulting to Hebrew."""
    settings = database.get_user_settings(chat_id)
    return settings["language"] if settings else "he"


def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("en", "btn_lang_en"), callback_data="lang_en"),
        InlineKeyboardButton("🇮🇱 עברית",            callback_data="lang_he"),
    ]])


def _format_last_sent(last_sent: datetime | None, lang: str) -> str:
    """Convert a UTC-aware datetime from PostgreSQL to a display string."""
    if last_sent is None:
        return t(lang, "last_sent_never")
    il_time = last_sent.astimezone(ISRAEL_TZ)
    return il_time.strftime("%d/%m/%Y %H:%M")


# ---------------------------------------------------------------------------
# Job callback — fires on every scheduled interval
# ---------------------------------------------------------------------------


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deliver the reminder and update last_sent in PostgreSQL."""
    job         = context.job
    chat_id     = job.chat_id
    reminder_id = job.data["reminder_id"]
    lang        = _get_lang(chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text=t(lang, "notification", message=job.data["message"]),
        parse_mode="Markdown",
    )

    database.update_last_sent(reminder_id)
    logger.info("Reminder #%d delivered to chat %d.", reminder_id, chat_id)


# ---------------------------------------------------------------------------
# Scheduling helpers
# ---------------------------------------------------------------------------


def _compute_first_run(start_date: str, send_time: str, interval_days: int) -> datetime:
    """Return the next fire datetime (tz-aware, Israel time).

    If the original start_date/send_time lies in the past the function
    advances it by the minimum number of full intervals so the returned
    datetime is strictly in the future, preserving the original cadence.
    """
    hour,  minute = map(int, send_time.split(":"))
    year, month, day = map(int, start_date.split("-"))

    # localize (not replace) so pytz applies the correct DST offset
    first_run = ISRAEL_TZ.localize(datetime(year, month, day, hour, minute))
    now       = datetime.now(ISRAEL_TZ)

    if first_run <= now:
        elapsed        = (now - first_run).total_seconds()
        interval_secs  = interval_days * 86_400
        intervals_done = int(elapsed // interval_secs) + 1
        first_run      += timedelta(seconds=intervals_done * interval_secs)

    return first_run


def schedule_reminder(job_queue, reminder: dict) -> None:
    """Register a reminder dict as a repeating JobQueue job."""
    chat_id     = reminder["chat_id"]
    reminder_id = reminder["id"]
    first_run   = _compute_first_run(
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
        reminder_id, chat_id, first_run.isoformat(),
    )


def _cancel_job(job_queue, chat_id: int, reminder_id: int) -> None:
    for job in job_queue.get_jobs_by_name(f"reminder_{chat_id}_{reminder_id}"):
        job.schedule_removal()


# ---------------------------------------------------------------------------
# Startup — rebuild JobQueue from PostgreSQL
# ---------------------------------------------------------------------------


def load_jobs_from_db(job_queue) -> None:
    """Bridge between persistence and scheduling.

    Called after Application.build() (JobQueue exists) but before
    run_polling() (scheduler not yet running).  Every row in the
    reminders table is re-registered so no reminder is lost across
    restarts.
    """
    reminders = database.get_all_reminders()
    loaded    = 0
    for reminder in reminders:
        try:
            schedule_reminder(job_queue, reminder)
            loaded += 1
        except Exception:
            logger.exception("Could not reschedule reminder #%d — skipping", reminder["id"])
    logger.info("Reloaded %d / %d reminder(s) from PostgreSQL.", loaded, len(reminders))


# ---------------------------------------------------------------------------
# Shared UI helper — reminder list
# ---------------------------------------------------------------------------


async def _send_reminder_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send one message per reminder with an inline Delete button.

    Used by both /list and the 'Manage' callback so rendering lives in
    one place.
    """
    reminders = database.get_reminders_by_chat_id(chat_id)
    lang      = _get_lang(chat_id)

    if not reminders:
        await context.bot.send_message(chat_id, t(lang, "no_reminders"))
        return

    await context.bot.send_message(
        chat_id,
        t(lang, "list_header", count=len(reminders)),
        parse_mode="Markdown",
    )

    for r in reminders:
        card = t(
            lang, "reminder_card",
            id=r["id"],
            message=r["message"],
            start_date=r["start_date"],
            send_time=r["send_time"],
            interval_days=r["interval_days"],
            last_sent=_format_last_sent(r["last_sent"], lang),
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                t(lang, "btn_delete", id=r["id"]),
                callback_data=f"{CB_DELETE_PREFIX}{r['id']}",
            )
        ]])
        await context.bot.send_message(
            chat_id, card,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


async def _show_welcome(chat_id: int, lang: str, reply_func) -> None:
    """Send the welcome message with the Manage button using reply_func."""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_manage"), callback_data=CB_SHOW_LIST),
    ]])
    await reply_func(
        t(lang, "welcome"),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show welcome message; ask for language on the very first visit."""
    chat_id  = update.effective_chat.id
    settings = database.get_user_settings(chat_id)

    if settings is None:
        # First-time user — language not yet chosen
        await update.message.reply_text(
            "🌐 Please choose your language / אנא בחר שפה:",
            reply_markup=_lang_keyboard(),
        )
    else:
        await _show_welcome(chat_id, settings["language"], update.message.reply_text)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_reminder_list(update.effective_chat.id, context)


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Let returning users switch language at any time."""
    chat_id = update.effective_chat.id
    lang    = _get_lang(chat_id)
    await update.message.reply_text(
        t(lang, "choose_lang"),
        reply_markup=_lang_keyboard(),
    )


# ---------------------------------------------------------------------------
# Inline-keyboard callbacks
# ---------------------------------------------------------------------------


async def callback_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save the chosen language and show the welcome screen."""
    query   = update.callback_query
    await query.answer()

    lang    = query.data.removeprefix(CB_LANG_PREFIX)   # "lang_en" → "en"
    chat_id = query.message.chat_id

    database.set_user_language(chat_id, lang)
    await query.edit_message_text(t(lang, "lang_set"), parse_mode="Markdown")

    # Show welcome as a new message so the confirmation stays visible
    await _show_welcome(chat_id, lang, query.message.reply_text)


async def callback_show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'Manage My Reminders' button pressed from /start."""
    query = update.callback_query
    await query.answer()
    await _send_reminder_list(query.message.chat_id, context)


async def callback_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a reminder via its inline button.

    Removes the row from PostgreSQL, cancels the live job, and edits the
    reminder card in-place so the button disappears immediately.
    """
    query       = update.callback_query
    await query.answer()

    reminder_id = int(query.data.removeprefix(CB_DELETE_PREFIX))
    chat_id     = query.message.chat_id
    lang        = _get_lang(chat_id)

    deleted = database.delete_reminder(reminder_id, chat_id)

    if deleted:
        _cancel_job(context.job_queue, chat_id, reminder_id)
        await query.edit_message_text(
            t(lang, "deleted", id=reminder_id), parse_mode="Markdown",
        )
        logger.info("Reminder #%d deleted by chat %d.", reminder_id, chat_id)
    else:
        await query.edit_message_text(
            t(lang, "not_found", id=reminder_id), parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# Conversation wizard — /new
# ---------------------------------------------------------------------------


async def conv_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    lang = _get_lang(update.effective_chat.id)
    await update.message.reply_text(t(lang, "wizard_intro"))
    await update.message.reply_text(t(lang, "wizard_step1"), parse_mode="Markdown")
    return ASK_MESSAGE


async def conv_received_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["message"] = update.message.text.strip()
    lang = _get_lang(update.effective_chat.id)
    await update.message.reply_text(t(lang, "wizard_step2"), parse_mode="Markdown")
    return ASK_DATE


async def conv_received_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang      = _get_lang(update.effective_chat.id)
    date_text = update.message.text.strip()
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(t(lang, "err_date"), parse_mode="Markdown")
        return ASK_DATE

    context.user_data["start_date"] = date_text
    await update.message.reply_text(t(lang, "wizard_step3"), parse_mode="Markdown")
    return ASK_INTERVAL


async def conv_received_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _get_lang(update.effective_chat.id)
    try:
        interval = int(update.message.text.strip())
        if interval < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text(t(lang, "err_interval"))
        return ASK_INTERVAL

    context.user_data["interval_days"] = interval
    await update.message.reply_text(t(lang, "wizard_step4"), parse_mode="Markdown")
    return ASK_TIME


async def conv_received_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang      = _get_lang(update.effective_chat.id)
    time_text = update.message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await update.message.reply_text(t(lang, "err_time"), parse_mode="Markdown")
        return ASK_TIME

    chat_id      = update.effective_chat.id
    message      = context.user_data["message"]
    start_date   = context.user_data["start_date"]
    interval_days = context.user_data["interval_days"]

    reminder_id = database.add_reminder(chat_id, message, start_date, interval_days, time_text)
    reminder    = {
        "id": reminder_id, "chat_id": chat_id, "message": message,
        "start_date": start_date, "interval_days": interval_days, "send_time": time_text,
    }
    schedule_reminder(context.job_queue, reminder)
    context.user_data.clear()

    await update.message.reply_text(
        t(lang, "saved",
          id=reminder_id, message=message, start_date=start_date,
          send_time=time_text, interval_days=interval_days),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _get_lang(update.effective_chat.id)
    context.user_data.clear()
    await update.message.reply_text(t(lang, "cancelled"), reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------


def main() -> None:
    database.init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # ── Conversation wizard ──────────────────────────────────────────
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

    # ── Commands ─────────────────────────────────────────────────────
    application.add_handler(CommandHandler("start",    cmd_start))
    application.add_handler(CommandHandler("list",     cmd_list))
    application.add_handler(CommandHandler("language", cmd_language))

    # ── Inline callbacks (most-specific patterns first) ───────────────
    application.add_handler(CallbackQueryHandler(callback_set_language, pattern=r"^lang_(en|he)$"))
    application.add_handler(CallbackQueryHandler(callback_show_list,    pattern=rf"^{CB_SHOW_LIST}$"))
    application.add_handler(CallbackQueryHandler(callback_delete,        pattern=r"^del_\d+$"))

    # ── Wizard ───────────────────────────────────────────────────────
    application.add_handler(conv_handler)

    # Re-register every persisted reminder before the scheduler starts.
    load_jobs_from_db(application.job_queue)

    logger.info("Bot is running — press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
