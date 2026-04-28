"""PostgreSQL persistence layer for the Telegram Reminder Bot.

Environment variables (all read at call-time, never at import):
    DB_HOST     — default: localhost
    DB_PORT     — default: 5432
    DB_NAME     — default: reminders
    DB_USER     — default: postgres
    DB_PASS     — required (no default)

Every public function opens, uses, and closes its own connection so the
module is safe to call from asyncio without shared mutable state.
"""

import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ.get("DB_NAME", "reminders"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ["DB_PASS"],
    )


@contextmanager
def _get_conn():
    """Yield a connection; commit on clean exit, rollback + close on error."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def init_db(retries: int = 6, backoff: float = 2.0) -> None:
    """Create all tables if they do not already exist.

    Retries with exponential back-off so the bot container can start
    concurrently with the postgres container without crashing.
    """
    for attempt in range(1, retries + 1):
        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS reminders (
                            id            SERIAL          PRIMARY KEY,
                            chat_id       BIGINT          NOT NULL,
                            message       TEXT            NOT NULL,
                            start_date    TEXT            NOT NULL,
                            interval_days INTEGER         NOT NULL,
                            send_time     TEXT            NOT NULL,
                            last_sent     TIMESTAMPTZ
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_settings (
                            chat_id  BIGINT      PRIMARY KEY,
                            language VARCHAR(5)  NOT NULL DEFAULT 'he'
                        )
                    """)
            logger.info("Database schema ready.")
            return
        except psycopg2.OperationalError as exc:
            if attempt == retries:
                raise
            wait = backoff ** attempt
            logger.warning(
                "DB not ready (attempt %d/%d) — retrying in %.0fs: %s",
                attempt, retries, wait, exc,
            )
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


def add_reminder(
    chat_id: int,
    message: str,
    start_date: str,
    interval_days: int,
    send_time: str,
) -> int:
    """Insert a reminder and return the generated id."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reminders (chat_id, message, start_date, interval_days, send_time)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id""",
                (chat_id, message, start_date, interval_days, send_time),
            )
            return cur.fetchone()[0]


def get_reminders_by_chat_id(chat_id: int) -> list[dict]:
    """Return all reminders for one user, ordered by id."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE chat_id = %s ORDER BY id",
                (chat_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_all_reminders() -> list[dict]:
    """Return every reminder row (used on startup to rebuild the JobQueue)."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM reminders ORDER BY id")
            return [dict(r) for r in cur.fetchall()]


def delete_reminder(reminder_id: int, chat_id: int) -> bool:
    """Delete a reminder that belongs to chat_id.

    Returns True when a row was actually removed.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM reminders WHERE id = %s AND chat_id = %s",
                (reminder_id, chat_id),
            )
            return cur.rowcount > 0


def update_last_sent(reminder_id: int) -> None:
    """Stamp the reminder with the current UTC time after a successful delivery."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reminders SET last_sent = NOW() WHERE id = %s",
                (reminder_id,),
            )


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------


def get_user_settings(chat_id: int) -> dict | None:
    """Return the settings row for chat_id, or None if first-time user."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM user_settings WHERE chat_id = %s",
                (chat_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def set_user_language(chat_id: int, language: str) -> None:
    """Upsert the user's preferred language (ISO 639-1 code)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO user_settings (chat_id, language)
                   VALUES (%s, %s)
                   ON CONFLICT (chat_id)
                   DO UPDATE SET language = EXCLUDED.language""",
                (chat_id, language),
            )
