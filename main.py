"""Telegram Reminder Bot — main entry point.

All Telegram messages use HTML parse_mode.  User-supplied content is always
passed through _e() before string interpolation to prevent broken markup.

Commands:
    /start      — welcome screen (asks language on first visit)
    /new        — 4-step wizard to schedule a periodic reminder
    /list       — reminder manager: card view + edit / delete buttons
    /language   — change language preference
    /cancel     — abort any active wizard
"""

import html as _html
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

# /new wizard states
ASK_MESSAGE, ASK_DATE, ASK_INTERVAL, ASK_TIME = range(4)

# edit wizard states  (separate range to avoid collision)
EDIT_FIELD, EDIT_VALUE = range(10, 12)

# Callback-data prefixes / tokens
CB_SHOW_LIST   = "show_list"
CB_LANG_PREFIX = "lang_"
CB_DEL_PREFIX  = "del_"
CB_EDIT_PREFIX = "edit_"
CB_EF_PREFIX   = "ef_"          # edit-field sub-menu: ef_{id}_{field}

# ---------------------------------------------------------------------------
# Helpers: localisation, HTML safety, time formatting
# ---------------------------------------------------------------------------


def _get_lang(chat_id: int) -> str:
    """Return the user's saved language, defaulting to Hebrew."""
    s = database.get_user_settings(chat_id)
    return s["language"] if s else "he"


def _e(value: object) -> str:
    """Escape user content for safe HTML interpolation inside t() templates.

    Two things happen:
      1. HTML-escape  < > & → &lt; &gt; &amp;  (safe for parse_mode=HTML)
      2. Brace-escape { } → {{ }}               (safe for str.format inside t())
    """
    return _html.escape(str(value)).replace("{", "{{").replace("}", "}}")


def _format_dt(dt: datetime | None, lang: str, never_key: str = "last_sent_never") -> str:
    """Convert a UTC-aware datetime from PostgreSQL to DD/MM/YYYY HH:MM (IL)."""
    if dt is None:
        return t(lang, never_key)
    return dt.astimezone(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")


def _get_next_run(job_queue, reminder_id: int, lang: str) -> str:
    """Look up the next scheduled fire time for a job from the JobQueue."""
    jobs = job_queue.get_jobs_by_name(f"job_{reminder_id}")
    if not jobs or jobs[0].next_t is None:
        return t(lang, "next_run_unknown")
    return jobs[0].next_t.astimezone(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")


def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("en", "btn_lang_en"), callback_data="lang_en"),
        InlineKeyboardButton("🇮🇱 עברית",            callback_data="lang_he"),
    ]])


# ---------------------------------------------------------------------------
# Job callback — fires on every scheduled interval
# ---------------------------------------------------------------------------


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deliver a reminder notification and update last_sent in PostgreSQL."""
    job         = context.job
    chat_id     = job.chat_id
    reminder_id = job.data["reminder_id"]
    lang        = _get_lang(chat_id)

    await context.bot.send_message(
        chat_id=chat_id,
        text=t(lang, "notification", message=_e(job.data["message"])),
        parse_mode="HTML",
    )
    database.update_last_sent(reminder_id)
    logger.info("Reminder #%d delivered to chat %d.", reminder_id, chat_id)


# ---------------------------------------------------------------------------
# Scheduling helpers
# ---------------------------------------------------------------------------


def _compute_first_run(start_date: str, send_time: str, interval_days: int) -> datetime:
    """Return the next fire time (tz-aware Israel time), always in the future.

    If the original start_date/send_time is in the past the datetime is
    advanced by the minimum number of complete intervals to clear 'now'.
    """
    hour, minute      = map(int, send_time.split(":"))
    year, month, day  = map(int, start_date.split("-"))
    first_run         = ISRAEL_TZ.localize(datetime(year, month, day, hour, minute))
    now               = datetime.now(ISRAEL_TZ)

    if first_run <= now:
        elapsed        = (now - first_run).total_seconds()
        interval_secs  = interval_days * 86_400
        n              = int(elapsed // interval_secs) + 1
        first_run      += timedelta(seconds=n * interval_secs)

    return first_run


def schedule_reminder(job_queue, reminder: dict) -> None:
    """Register a reminder dict as a repeating JobQueue job.

    Job name: job_{reminder_id}  — unique because reminder ids are SERIAL PKs.
    """
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
        name=f"job_{reminder_id}",
        chat_id=chat_id,
        data={"message": reminder["message"], "reminder_id": reminder_id},
    )
    logger.info(
        "Scheduled reminder #%d for chat %d — next fire at %s",
        reminder_id, chat_id, first_run.isoformat(),
    )


def _cancel_job(job_queue, reminder_id: int) -> None:
    """Cancel the live JobQueue entry for a reminder (if it exists)."""
    for job in job_queue.get_jobs_by_name(f"job_{reminder_id}"):
        job.schedule_removal()


# ---------------------------------------------------------------------------
# Startup — rebuild JobQueue from PostgreSQL
# ---------------------------------------------------------------------------


def load_jobs_from_db(job_queue) -> None:
    """Called after Application.build() but before run_polling().

    Re-registers every DB row as a repeating job so no reminder is
    silently lost across restarts.
    """
    all_reminders = database.get_all_reminders()
    loaded        = 0
    for reminder in all_reminders:
        try:
            schedule_reminder(job_queue, reminder)
            loaded += 1
        except Exception:
            logger.exception("Could not reschedule reminder #%d — skipping", reminder["id"])
    logger.info("Reloaded %d / %d reminder(s) from PostgreSQL.", loaded, len(all_reminders))


# ---------------------------------------------------------------------------
# Shared UI — reminder list
# ---------------------------------------------------------------------------


async def _send_reminder_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render one card per reminder with ✏️ Edit and ❌ Delete buttons.

    Called by /list command AND by the 'Manage' callback so the rendering
    logic lives in exactly one place.
    """
    reminders = database.get_reminders_by_chat_id(chat_id)
    lang      = _get_lang(chat_id)

    if not reminders:
        await context.bot.send_message(chat_id, t(lang, "no_reminders"))
        return

    await context.bot.send_message(
        chat_id,
        t(lang, "list_header", count=len(reminders)),
        parse_mode="HTML",
    )

    for r in reminders:
        card = t(
            lang, "reminder_card",
            message=_e(r["message"]),
            start_date=r["start_date"],
            interval_days=r["interval_days"],
            send_time=r["send_time"],
            last_sent=_format_dt(r["last_sent"], lang),
            next_run=_get_next_run(context.job_queue, r["id"], lang),
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "btn_edit"),   callback_data=f"{CB_EDIT_PREFIX}{r['id']}"),
            InlineKeyboardButton(t(lang, "btn_delete"), callback_data=f"{CB_DEL_PREFIX}{r['id']}"),
        ]])
        await context.bot.send_message(
            chat_id, card,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


async def _show_welcome(chat_id: int, lang: str, send_fn) -> None:
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_manage"), callback_data=CB_SHOW_LIST),
    ]])
    await send_fn(t(lang, "welcome"), parse_mode="HTML", reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id  = update.effective_chat.id
    settings = database.get_user_settings(chat_id)
    if settings is None:
        await update.message.reply_text(
            "🌐 Please choose your language / אנא בחר שפה:",
            reply_markup=_lang_keyboard(),
        )
    else:
        await _show_welcome(chat_id, settings["language"], update.message.reply_text)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_reminder_list(update.effective_chat.id, context)


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _get_lang(update.effective_chat.id)
    await update.message.reply_text(t(lang, "choose_lang"), reply_markup=_lang_keyboard())


# ---------------------------------------------------------------------------
# Inline callbacks — language, list, delete
# ---------------------------------------------------------------------------


async def callback_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query   = update.callback_query
    await query.answer()
    lang    = query.data.removeprefix(CB_LANG_PREFIX)
    chat_id = query.message.chat_id
    database.set_user_language(chat_id, lang)
    await query.edit_message_text(t(lang, "lang_set"), parse_mode="HTML")
    await _show_welcome(chat_id, lang, query.message.reply_text)


async def callback_show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _send_reminder_list(query.message.chat_id, context)


async def callback_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a reminder: DB row + live job.  Edits the card in-place."""
    query       = update.callback_query
    await query.answer()
    reminder_id = int(query.data.removeprefix(CB_DEL_PREFIX))
    chat_id     = query.message.chat_id
    lang        = _get_lang(chat_id)

    if database.delete_reminder(reminder_id, chat_id):
        _cancel_job(context.job_queue, reminder_id)
        await query.edit_message_text(t(lang, "deleted", id=reminder_id), parse_mode="HTML")
        logger.info("Reminder #%d deleted by chat %d.", reminder_id, chat_id)
    else:
        await query.edit_message_text(t(lang, "not_found", id=reminder_id), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Edit wizard — ConversationHandler (entry via callback, value via message)
# ---------------------------------------------------------------------------


async def edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry: user taps ✏️ on a reminder card → show field selector."""
    query       = update.callback_query
    await query.answer()
    reminder_id = int(query.data.removeprefix(CB_EDIT_PREFIX))
    chat_id     = query.message.chat_id
    lang        = _get_lang(chat_id)

    reminder = database.get_reminder_by_id(reminder_id, chat_id)
    if not reminder:
        await query.answer(t(lang, "not_found", id=reminder_id), show_alert=True)
        return ConversationHandler.END

    context.user_data["editing"] = {"reminder_id": reminder_id}

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_edit_message"),  callback_data=f"{CB_EF_PREFIX}{reminder_id}_message")],
        [InlineKeyboardButton(t(lang, "btn_edit_date"),     callback_data=f"{CB_EF_PREFIX}{reminder_id}_start_date")],
        [InlineKeyboardButton(t(lang, "btn_edit_interval"), callback_data=f"{CB_EF_PREFIX}{reminder_id}_interval_days")],
        [InlineKeyboardButton(t(lang, "btn_edit_time"),     callback_data=f"{CB_EF_PREFIX}{reminder_id}_send_time")],
    ])
    await context.bot.send_message(
        chat_id,
        t(lang, "edit_choose_field", id=reminder_id),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return EDIT_FIELD


async def edit_field_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State EDIT_FIELD: user picks a field → show current value, ask for new."""
    query   = update.callback_query
    await query.answer()

    # callback_data: "ef_{id}_{field}"  — split on first two underscores only
    _, id_str, field = query.data.split("_", 2)
    reminder_id      = int(id_str)
    chat_id          = query.message.chat_id
    lang             = _get_lang(chat_id)

    reminder      = database.get_reminder_by_id(reminder_id, chat_id)
    current_value = str(reminder[field]) if reminder else "—"

    context.user_data["editing"]["field"] = field

    await query.edit_message_text(
        t(lang, "edit_current_value",
          field=t(lang, f"field_{field}"),
          value=_e(current_value)),
        parse_mode="HTML",
    )
    return EDIT_VALUE


async def edit_save_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """State EDIT_VALUE: validate + persist the new value, reschedule if needed."""
    editing     = context.user_data.get("editing", {})
    reminder_id = editing.get("reminder_id")
    field       = editing.get("field")
    chat_id     = update.effective_chat.id
    lang        = _get_lang(chat_id)

    if not reminder_id or not field:
        return ConversationHandler.END

    raw       = update.message.text.strip()
    new_value = raw                         # may be overwritten for integer fields

    # --- per-field validation ---
    if field == "start_date":
        try:
            datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(t(lang, "err_date"), parse_mode="HTML")
            return EDIT_VALUE

    elif field == "interval_days":
        try:
            new_value = int(raw)
            if new_value < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text(t(lang, "err_interval"))
            return EDIT_VALUE

    elif field == "send_time":
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError:
            await update.message.reply_text(t(lang, "err_time"), parse_mode="HTML")
            return EDIT_VALUE

    # --- persist ---
    updated = database.update_reminder_field(reminder_id, chat_id, field, new_value)

    # --- reschedule when a scheduling field changed ---
    if updated and field in ("start_date", "interval_days", "send_time"):
        _cancel_job(context.job_queue, reminder_id)
        refreshed = database.get_reminder_by_id(reminder_id, chat_id)
        if refreshed:
            schedule_reminder(context.job_queue, refreshed)

    context.user_data.pop("editing", None)
    key = "edit_saved" if updated else "not_found"
    await update.message.reply_text(t(lang, key, id=reminder_id), parse_mode="HTML")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /new wizard — ConversationHandler
# ---------------------------------------------------------------------------


async def conv_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    lang = _get_lang(update.effective_chat.id)
    await update.message.reply_text(t(lang, "wizard_intro"))
    await update.message.reply_text(t(lang, "wizard_step1"), parse_mode="HTML")
    return ASK_MESSAGE


async def conv_received_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["message"] = update.message.text.strip()
    lang = _get_lang(update.effective_chat.id)
    await update.message.reply_text(t(lang, "wizard_step2"), parse_mode="HTML")
    return ASK_DATE


async def conv_received_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang      = _get_lang(update.effective_chat.id)
    date_text = update.message.text.strip()
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(t(lang, "err_date"), parse_mode="HTML")
        return ASK_DATE
    context.user_data["start_date"] = date_text
    await update.message.reply_text(t(lang, "wizard_step3"), parse_mode="HTML")
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
    await update.message.reply_text(t(lang, "wizard_step4"), parse_mode="HTML")
    return ASK_TIME


async def conv_received_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang      = _get_lang(update.effective_chat.id)
    time_text = update.message.text.strip()
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await update.message.reply_text(t(lang, "err_time"), parse_mode="HTML")
        return ASK_TIME

    chat_id       = update.effective_chat.id
    message       = context.user_data["message"]
    start_date    = context.user_data["start_date"]
    interval_days = context.user_data["interval_days"]

    reminder_id = database.add_reminder(chat_id, message, start_date, interval_days, time_text)
    schedule_reminder(context.job_queue, {
        "id": reminder_id, "chat_id": chat_id, "message": message,
        "start_date": start_date, "interval_days": interval_days, "send_time": time_text,
    })
    context.user_data.clear()

    await update.message.reply_text(
        t(lang, "saved",
          id=reminder_id, message=_e(message),
          start_date=start_date, send_time=time_text,
          interval_days=interval_days),
        parse_mode="HTML",
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

    # ── Edit wizard (callback entry → message value) ─────────────────
    edit_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_entry, pattern=r"^edit_\d+$")],
        states={
            EDIT_FIELD: [CallbackQueryHandler(
                edit_field_selected,
                pattern=r"^ef_\d+_(message|start_date|interval_days|send_time)$",
            )],
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save_value)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        per_message=False,
    )

    # ── New-reminder wizard ───────────────────────────────────────────
    new_handler = ConversationHandler(
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

    # ── Standalone inline callbacks (specific patterns, registered early) ──
    application.add_handler(CallbackQueryHandler(callback_set_language, pattern=r"^lang_(en|he)$"))
    application.add_handler(CallbackQueryHandler(callback_show_list,    pattern=rf"^{CB_SHOW_LIST}$"))
    application.add_handler(CallbackQueryHandler(callback_delete,       pattern=r"^del_\d+$"))

    # ── Conversation handlers ─────────────────────────────────────────
    application.add_handler(edit_handler)
    application.add_handler(new_handler)

    # Re-register all persisted reminders before the scheduler starts.
    load_jobs_from_db(application.job_queue)

    logger.info("Bot is running — press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
