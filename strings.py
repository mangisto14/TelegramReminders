"""Bilingual string catalogue (English / Hebrew).

Usage
-----
from strings import t

text = t("he", "welcome")
text = t("en", "saved", id=3, message="Buy milk", ...)
"""

STRINGS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------
    "en": {
        # ── General ───────────────────────────────────────────────────
        "welcome": (
            "👋 *Welcome to the Reminder Bot!*\n\n"
            "Commands:\n"
            "  /new        — Schedule a new reminder\n"
            "  /list       — Manage your reminders\n"
            "  /language   — Change language\n"
            "  /cancel     — Abort the current wizard\n\n"
            "_All times are in Israel time (Asia/Jerusalem)._"
        ),
        "btn_manage": "📋 Manage My Reminders",

        # ── Language selection ─────────────────────────────────────────
        "choose_lang": "🌐 Please choose your preferred language:",
        "btn_lang_en": "🇬🇧 English",
        "btn_lang_he": "🇮🇱 עברית",
        "lang_set":    "✅ Language set to *English*.",

        # ── Wizard ────────────────────────────────────────────────────
        "wizard_intro":    "Let's create a new reminder!",
        "wizard_step1":    "📝 *Step 1 / 4* — What message should I send you?",
        "wizard_step2":    "📅 *Step 2 / 4* — Start date?\nFormat: `YYYY-MM-DD` (e.g. `2025-06-01`)",
        "wizard_step3":    "🔄 *Step 3 / 4* — Repeat interval?\nEnter number of days (e.g. `3` for every 3 days):",
        "wizard_step4":    "⏰ *Step 4 / 4* — At what time? (Israel time)\nFormat: `HH:MM` (e.g. `09:00`)",
        "err_date":        "❌ Invalid date. Please use the format `YYYY-MM-DD`:",
        "err_interval":    "❌ Please enter a whole number greater than 0:",
        "err_time":        "❌ Invalid time. Please use `HH:MM` format (e.g. `09:00`):",
        "saved": (
            "✅ *Reminder #{id} saved!*\n\n"
            "📝 Message : {message}\n"
            "📅 Start   : `{start_date}` at `{send_time}` (IL time)\n"
            "🔄 Repeat  : every {interval_days} day(s)\n\n"
            "Use /list to manage your reminders."
        ),
        "cancelled": "❌ Cancelled. Use /new to start again.",

        # ── Reminder list ─────────────────────────────────────────────
        "list_header":    "📋 *Your reminders* ({count} active):",
        "no_reminders":   "You have no active reminders. Use /new to create one.",
        "reminder_card": (
            "🔔 *#{id}* — {message}\n"
            "📅 Start : `{start_date}` at `{send_time}`\n"
            "🔄 Every : {interval_days} day(s)\n"
            "📤 Last sent : {last_sent}"
        ),
        "last_sent_never": "Never",
        "btn_delete":      "❌ Delete #{id}",
        "deleted":         "🗑 Reminder *#{id}* has been deleted.",
        "not_found":       "⚠️ Reminder *#{id}* not found — it may already be deleted.",

        # ── Job notification ──────────────────────────────────────────
        "notification": "🔔 *Reminder:* {message}",
    },

    # ------------------------------------------------------------------
    "he": {
        # ── General ───────────────────────────────────────────────────
        "welcome": (
            "👋 *ברוכים הבאים לבוט תזכורות!*\n\n"
            "פקודות:\n"
            "  /new        — צור תזכורת חדשה\n"
            "  /list       — נהל את התזכורות שלך\n"
            "  /language   — שנה שפה\n"
            "  /cancel     — בטל את הפעולה הנוכחית\n\n"
            "_כל השעות בשעון ישראל (Asia/Jerusalem)._"
        ),
        "btn_manage": "📋 נהל את התזכורות שלי",

        # ── Language selection ─────────────────────────────────────────
        "choose_lang": "🌐 אנא בחר את השפה המועדפת עליך:",
        "btn_lang_en": "🇬🇧 English",
        "btn_lang_he": "🇮🇱 עברית",
        "lang_set":    "✅ השפה הוגדרה ל*עברית*.",

        # ── Wizard ────────────────────────────────────────────────────
        "wizard_intro":    "בואו ניצור תזכורת חדשה!",
        "wizard_step1":    "📝 *שלב 1 / 4* — מה ההודעה שאשלח לך?",
        "wizard_step2":    "📅 *שלב 2 / 4* — תאריך התחלה?\nפורמט: `YYYY-MM-DD` (לדוגמה: `2025-06-01`)",
        "wizard_step3":    "🔄 *שלב 3 / 4* — כל כמה ימים?\nהזן מספר ימים (לדוגמה: `3` לכל 3 ימים):",
        "wizard_step4":    "⏰ *שלב 4 / 4* — באיזו שעה? (שעון ישראל)\nפורמט: `HH:MM` (לדוגמה: `09:00`)",
        "err_date":        "❌ תאריך לא תקין. אנא השתמש בפורמט `YYYY-MM-DD`:",
        "err_interval":    "❌ אנא הזן מספר שלם גדול מ-0:",
        "err_time":        "❌ שעה לא תקינה. אנא השתמש בפורמט `HH:MM` (לדוגמה: `09:00`):",
        "saved": (
            "✅ *תזכורת #{id} נשמרה!*\n\n"
            "📝 הודעה   : {message}\n"
            "📅 התחלה   : `{start_date}` בשעה `{send_time}` (שעון ישראל)\n"
            "🔄 חוזרת   : כל {interval_days} יום/ימים\n\n"
            "השתמש ב-/list לניהול התזכורות."
        ),
        "cancelled": "❌ בוטל. השתמש ב-/new כדי להתחיל מחדש.",

        # ── Reminder list ─────────────────────────────────────────────
        "list_header":    "📋 *התזכורות שלך* ({count} פעילות):",
        "no_reminders":   "אין לך תזכורות פעילות. השתמש ב-/new כדי ליצור אחת.",
        "reminder_card": (
            "🔔 *#{id}* — {message}\n"
            "📅 התחלה       : `{start_date}` בשעה `{send_time}`\n"
            "🔄 חוזרת       : כל {interval_days} יום/ימים\n"
            "📤 נשלחה לאחרונה: {last_sent}"
        ),
        "last_sent_never": "מעולם לא",
        "btn_delete":      "❌ מחק #{id}",
        "deleted":         "🗑 תזכורת *#{id}* נמחקה.",
        "not_found":       "⚠️ תזכורת *#{id}* לא נמצאה — ייתכן שכבר נמחקה.",

        # ── Job notification ──────────────────────────────────────────
        "notification": "🔔 *תזכורת:* {message}",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    """Look up *key* in *lang* (falls back to Hebrew) and interpolate kwargs."""
    catalogue = STRINGS.get(lang, STRINGS["he"])
    template = catalogue.get(key, key)
    return template.format(**kwargs) if kwargs else template
