import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("DATABASE_PATH", "reminders.db"))


def init_db() -> None:
    """Create the reminders table if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       INTEGER NOT NULL,
                message       TEXT    NOT NULL,
                start_date    TEXT    NOT NULL,
                interval_days INTEGER NOT NULL,
                send_time     TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def add_reminder(
    chat_id: int,
    message: str,
    start_date: str,
    interval_days: int,
    send_time: str,
) -> int:
    """Insert a new reminder and return its auto-generated id."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO reminders (chat_id, message, start_date, interval_days, send_time)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, message, start_date, interval_days, send_time),
        )
        conn.commit()
        return cursor.lastrowid


def get_reminders_by_chat_id(chat_id: int) -> list[dict]:
    """Return all reminders belonging to a specific user."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM reminders WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_reminders() -> list[dict]:
    """Return every reminder in the database (used on startup to reload jobs)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM reminders ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def delete_reminder(reminder_id: int, chat_id: int) -> bool:
    """Delete a reminder by id, but only if it belongs to chat_id.

    Returns True when a row was actually deleted.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "DELETE FROM reminders WHERE id = ? AND chat_id = ?",
            (reminder_id, chat_id),
        )
        conn.commit()
    return cursor.rowcount > 0
