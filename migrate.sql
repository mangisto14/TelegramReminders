-- ---------------------------------------------------------------------------
-- Migration script for TelegramReminders
-- Safe to run on an existing database — all statements are idempotent.
-- ---------------------------------------------------------------------------

-- 1. Add last_sent column to reminders (upgrading from v1 / SQLite migration)
ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS last_sent TIMESTAMPTZ;

-- 2. Create user_settings table if missing (upgrading from v1)
CREATE TABLE IF NOT EXISTS user_settings (
    chat_id  BIGINT     PRIMARY KEY,
    language VARCHAR(5) NOT NULL DEFAULT 'he'
);
