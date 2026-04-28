"""Bilingual string catalogue — all strings use HTML formatting.

Usage
-----
from strings import t

text = t("he", "welcome")
text = t("en", "reminder_card", message="...", start_date="...", ...)
"""

import html as _html

STRINGS: dict[str, dict[str, str]] = {
    # ══════════════════════════════════════════════════════════════════
    "en": {
        # ── General ───────────────────────────────────────────────────
        "welcome": (
            "👋 <b>Welcome to the Reminder Bot!</b>\n\n"
            "Commands:\n"
            "  /new        — Schedule a new reminder\n"
            "  /list       — Manage your reminders\n"
            "  /language   — Change language\n"
            "  /cancel     — Abort the current wizard\n\n"
            "<i>All times are in Israel time (Asia/Jerusalem).</i>"
        ),
        "btn_manage": "📋 Manage My Reminders",

        # ── Language selection ─────────────────────────────────────────
        "choose_lang": "🌐 Please choose your preferred language:",
        "btn_lang_en": "🇬🇧 English",
        "btn_lang_he": "🇮🇱 עברית",
        "lang_set":    "✅ Language set to <b>English</b>.",

        # ── Wizard ────────────────────────────────────────────────────
        "wizard_intro":    "Let's create a new reminder!",
        "wizard_step1":    "📝 <b>Step 1 / 4</b> — What message should I send you?",
        "wizard_step2":    "📅 <b>Step 2 / 4</b> — Start date?\nFormat: <code>YYYY-MM-DD</code>  (e.g. <code>2025-06-01</code>)",
        "wizard_step3":    "🔄 <b>Step 3 / 4</b> — Repeat interval?\nEnter number of days (e.g. <code>3</code> for every 3 days):",
        "wizard_step4":    "⏰ <b>Step 4 / 4</b> — At what time? (Israel time)\nFormat: <code>HH:MM</code>  (e.g. <code>09:00</code>)",
        "err_date":        "❌ Invalid date. Please use <code>YYYY-MM-DD</code> format:",
        "err_interval":    "❌ Please enter a whole number greater than 0:",
        "err_time":        "❌ Invalid time. Please use <code>HH:MM</code> format (e.g. <code>09:00</code>):",
        "saved": (
            "✅ <b>Reminder #{id} saved!</b>\n\n"
            "📝 Message : {message}\n"
            "📅 Start   : <code>{start_date}</code> at <code>{send_time}</code> (IL time)\n"
            "🔄 Repeat  : every {interval_days} day(s)\n\n"
            "Use /list to manage your reminders."
        ),
        "cancelled": "❌ Cancelled. Use /new to start again.",

        # ── Reminder list ─────────────────────────────────────────────
        "list_header":  "📋 <b>Your reminders</b> ({count} active):",
        "no_reminders": "You have no active reminders. Use /new to create one.",
        "reminder_card": (
            "🔔 <b>Reminder:</b> {message}\n"
            "📅 <b>Start:</b> {start_date}\n"
            "🔄 <b>Frequency:</b> every {interval_days} days\n"
            "⏰ <b>Send time:</b> {send_time}\n"
            "─────────────────\n"
            "🕒 <b>Last sent:</b> {last_sent}\n"
            "🚀 <b>Next send:</b> {next_run}"
        ),
        "last_sent_never":  "Never sent",
        "next_run_unknown": "—",
        "btn_edit":         "✏️ Edit",
        "btn_delete":       "❌ Delete",
        "deleted":          "🗑 Reminder <b>#{id}</b> has been deleted.",
        "not_found":        "⚠️ Reminder <b>#{id}</b> not found — it may already be deleted.",

        # ── Edit wizard ───────────────────────────────────────────────
        "edit_choose_field":  "✏️ <b>Edit reminder #{id}</b>\nWhat would you like to change?",
        "btn_edit_message":   "📝 Message",
        "btn_edit_date":      "📅 Start date",
        "btn_edit_interval":  "🔄 Interval (days)",
        "btn_edit_time":      "⏰ Send time",
        "field_message":      "Message",
        "field_start_date":   "Start date",
        "field_interval_days":"Interval",
        "field_send_time":    "Send time",
        "edit_current_value": "Current <b>{field}</b>: <code>{value}</code>\n\nEnter the new value:",
        "edit_saved":         "✅ Reminder <b>#{id}</b> has been updated.",

        # ── Job notification ──────────────────────────────────────────
        "notification": "🔔 <b>Reminder:</b> {message}",
    },

    # ══════════════════════════════════════════════════════════════════
    "he": {
        # ── General ───────────────────────────────────────────────────
        "welcome": (
            "👋 <b>ברוכים הבאים לבוט תזכורות!</b>\n\n"
            "פקודות:\n"
            "  /new        — צור תזכורת חדשה\n"
            "  /list       — נהל את התזכורות שלך\n"
            "  /language   — שנה שפה\n"
            "  /cancel     — בטל את הפעולה הנוכחית\n\n"
            "<i>כל השעות בשעון ישראל (Asia/Jerusalem).</i>"
        ),
        "btn_manage": "📋 נהל את התזכורות שלי",

        # ── Language selection ─────────────────────────────────────────
        "choose_lang": "🌐 אנא בחר את השפה המועדפת עליך:",
        "btn_lang_en": "🇬🇧 English",
        "btn_lang_he": "🇮🇱 עברית",
        "lang_set":    "✅ השפה הוגדרה ל<b>עברית</b>.",

        # ── Wizard ────────────────────────────────────────────────────
        "wizard_intro":    "בואו ניצור תזכורת חדשה!",
        "wizard_step1":    "📝 <b>שלב 1 / 4</b> — מה ההודעה שאשלח לך?",
        "wizard_step2":    "📅 <b>שלב 2 / 4</b> — תאריך התחלה?\nפורמט: <code>YYYY-MM-DD</code>  (לדוגמה: <code>2025-06-01</code>)",
        "wizard_step3":    "🔄 <b>שלב 3 / 4</b> — כל כמה ימים?\nהזן מספר ימים (לדוגמה: <code>3</code> לכל 3 ימים):",
        "wizard_step4":    "⏰ <b>שלב 4 / 4</b> — באיזו שעה? (שעון ישראל)\nפורמט: <code>HH:MM</code>  (לדוגמה: <code>09:00</code>)",
        "err_date":        "❌ תאריך לא תקין. אנא השתמש בפורמט <code>YYYY-MM-DD</code>:",
        "err_interval":    "❌ אנא הזן מספר שלם גדול מ-0:",
        "err_time":        "❌ שעה לא תקינה. אנא השתמש בפורמט <code>HH:MM</code> (לדוגמה: <code>09:00</code>):",
        "saved": (
            "✅ <b>תזכורת #{id} נשמרה!</b>\n\n"
            "📝 הודעה   : {message}\n"
            "📅 התחלה   : <code>{start_date}</code> בשעה <code>{send_time}</code> (שעון ישראל)\n"
            "🔄 חוזרת   : כל {interval_days} יום/ימים\n\n"
            "השתמש ב-/list לניהול התזכורות."
        ),
        "cancelled": "❌ בוטל. השתמש ב-/new כדי להתחיל מחדש.",

        # ── Reminder list ─────────────────────────────────────────────
        "list_header":  "📋 <b>התזכורות שלך</b> ({count} פעילות):",
        "no_reminders": "אין לך תזכורות פעילות. השתמש ב-/new כדי ליצור אחת.",
        "reminder_card": (
            "🔔 <b>תזכורת:</b> {message}\n"
            "📅 <b>התחלה:</b> {start_date}\n"
            "🔄 <b>מחזוריות:</b> כל {interval_days} ימים\n"
            "⏰ <b>שעת שליחה:</b> {send_time}\n"
            "─────────────────\n"
            "🕒 <b>נשלח לאחרונה:</b> {last_sent}\n"
            "🚀 <b>שליחה הבאה:</b> {next_run}"
        ),
        "last_sent_never":  "טרם נשלח",
        "next_run_unknown": "—",
        "btn_edit":         "✏️ עריכה",
        "btn_delete":       "❌ מחיקה",
        "deleted":          "🗑 תזכורת <b>#{id}</b> נמחקה.",
        "not_found":        "⚠️ תזכורת <b>#{id}</b> לא נמצאה — ייתכן שכבר נמחקה.",

        # ── Edit wizard ───────────────────────────────────────────────
        "edit_choose_field":  "✏️ <b>עריכת תזכורת #{id}</b>\nמה ברצונך לשנות?",
        "btn_edit_message":   "📝 הודעה",
        "btn_edit_date":      "📅 תאריך התחלה",
        "btn_edit_interval":  "🔄 מחזוריות (ימים)",
        "btn_edit_time":      "⏰ שעת שליחה",
        "field_message":      "הודעה",
        "field_start_date":   "תאריך התחלה",
        "field_interval_days":"מחזוריות",
        "field_send_time":    "שעת שליחה",
        "edit_current_value": "<b>{field}</b> נוכחי: <code>{value}</code>\n\nהזן ערך חדש:",
        "edit_saved":         "✅ תזכורת <b>#{id}</b> עודכנה.",

        # ── Job notification ──────────────────────────────────────────
        "notification": "🔔 <b>תזכורת:</b> {message}",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Look up key in lang (falls back to Hebrew) and interpolate kwargs."""
    catalogue = STRINGS.get(lang, STRINGS["he"])
    template  = catalogue.get(key, key)
    return template.format(**kwargs) if kwargs else template
