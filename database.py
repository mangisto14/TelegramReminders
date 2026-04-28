"""PostgreSQL persistence layer for the Telegram Reminder Bot.

Connection parameters are read exclusively from environment variables:
    DB_HOST      — default: localhost
    DB_PORT      — default: 5432
    DB_NAME      — default: reminders
    DB_USER      — default: postgres
    DB_PASSWORD  — required (no default)

All public functions open, use, and close their own connection so the
module is safe to call from any asyncio context without a shared state.
"""

import logging
import os
import time
from contextlib import contextmanager

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
        password=os.environ["DB_PASSWORD"],
    )


@contextmanager
def _get_conn():
    """Yield a psycopg2 connection, commit on success, rollback on error."""
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
# Public API
# ---------------------------------------------------------------------------


def init_db(retries: int = 6, backoff: float = 2.0) -> None:
    """Create the reminders table (if absent).

    Retries with exponential back-off so the bot container can start
    before PostgreSQL is fully ready (useful outside Docker Compose).
    """
    for attempt in range(1, retries + 1):
        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS reminders (
                            id            SERIAL  PRIMARY KEY,
                            chat_id       BIGINT  NOT NULL,
                            message       TEXT    NOT NULL,
                            start_date    TEXT    NOT NULL,
                            interval_days INTEGER NOT NULL,
                            send_time     TEXT    NOT NULL
                        )
                    """)
            logger.info("Database ready.")
            return
        except psycopg2.OperationalError as exc:
            if attempt == retries:
                raise
            wait = backoff ** attempt
            logger.warning("DB not ready (attempt %d/%d) — retrying in %.0fs: %s", attempt, retries, wait, exc)
            time.sleep(wait)


def add_reminder(
    chat_id: int,
    message: str,
    start_date: str,
    interval_days: int,
    send_time: str,
) -> int:
    """Insert a new reminder row and return its generated id."""
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
    """Return all reminders that belong to a specific user, ordered by id."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM reminders WHERE chat_id = %s ORDER BY id",
                (chat_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_all_reminders() -> list[dict]:
    """Return every reminder row (called on startup to rebuild the JobQueue)."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM reminders ORDER BY id")
            return [dict(r) for r in cur.fetchall()]


def delete_reminder(reminder_id: int, chat_id: int) -> bool:
    """Delete a reminder only when it belongs to chat_id.

    Returns True if a row was actually removed, False when the reminder
    does not exist or belongs to a different user.
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM reminders WHERE id = %s AND chat_id = %s",
                (reminder_id, chat_id),
            )
            return cur.rowcount > 0
