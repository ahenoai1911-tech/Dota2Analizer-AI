"""
Shared DB module for main.py (FastAPI) and bot.py (python-telegram-bot).

Provides:
  - connection helper + context manager
  - schema bootstrapping (`ensure_schema`) — idempotent, used at startup
    (real migrations live in alembic/versions/*)
  - Bot persistence helpers: tracked players, notification prefs, last_seen cache
"""
from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Iterator, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")


# ── connection ───────────────────────────────────────────────────────────────
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


@contextmanager
def db_cursor(commit: bool = False) -> Iterator[psycopg2.extensions.cursor]:
    """Context manager для гарантированного закрытия соединения и rollback при ошибке."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── schema bootstrap (idempotent; prefer Alembic in production) ──────────────
BOT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bot_user_prefs (
    telegram_id   BIGINT PRIMARY KEY,
    notifications BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bot_tracked_players (
    telegram_id   BIGINT      NOT NULL,
    player_id     TEXT        NOT NULL,
    last_winrate  REAL,
    last_kda      REAL,
    added_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at  TIMESTAMP,
    PRIMARY KEY (telegram_id, player_id)
);

CREATE INDEX IF NOT EXISTS bot_tracked_players_tgid_idx
    ON bot_tracked_players (telegram_id);
"""


def ensure_bot_schema() -> None:
    """Создать таблицы бота если их нет (idempotent)."""
    if not DATABASE_URL:
        logger.warning("ensure_bot_schema: DATABASE_URL not set, skipping")
        return
    with db_cursor(commit=True) as c:
        c.execute(BOT_SCHEMA_SQL)


# ── bot user prefs ───────────────────────────────────────────────────────────
def get_notifications_enabled(telegram_id: int) -> bool:
    with db_cursor() as c:
        c.execute(
            "SELECT notifications FROM bot_user_prefs WHERE telegram_id = %s",
            (telegram_id,),
        )
        row = c.fetchone()
    if row is None:
        return True  # default on
    return bool(row["notifications"])


def set_notifications_enabled(telegram_id: int, enabled: bool) -> None:
    with db_cursor(commit=True) as c:
        c.execute(
            """
            INSERT INTO bot_user_prefs (telegram_id, notifications, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) DO UPDATE
                SET notifications = EXCLUDED.notifications,
                    updated_at    = CURRENT_TIMESTAMP
            """,
            (telegram_id, enabled),
        )


# ── tracked players ──────────────────────────────────────────────────────────
def add_tracked(telegram_id: int, player_id: str) -> bool:
    """Returns True if added, False if already tracked."""
    with db_cursor(commit=True) as c:
        c.execute(
            """
            INSERT INTO bot_tracked_players (telegram_id, player_id)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id, player_id) DO NOTHING
            RETURNING player_id
            """,
            (telegram_id, str(player_id)),
        )
        return c.fetchone() is not None


def remove_tracked(telegram_id: int, player_id: str) -> bool:
    with db_cursor(commit=True) as c:
        c.execute(
            "DELETE FROM bot_tracked_players WHERE telegram_id = %s AND player_id = %s",
            (telegram_id, str(player_id)),
        )
        return c.rowcount > 0


def clear_tracked(telegram_id: int) -> int:
    with db_cursor(commit=True) as c:
        c.execute("DELETE FROM bot_tracked_players WHERE telegram_id = %s", (telegram_id,))
        return c.rowcount


def list_tracked(telegram_id: int) -> List[str]:
    with db_cursor() as c:
        c.execute(
            "SELECT player_id FROM bot_tracked_players WHERE telegram_id = %s ORDER BY added_at",
            (telegram_id,),
        )
        return [r["player_id"] for r in c.fetchall()]


def tracked_count(telegram_id: int) -> int:
    with db_cursor() as c:
        c.execute(
            "SELECT COUNT(*) AS n FROM bot_tracked_players WHERE telegram_id = %s",
            (telegram_id,),
        )
        return int(c.fetchone()["n"])


def get_last_seen(telegram_id: int, player_id: str) -> Optional[dict]:
    with db_cursor() as c:
        c.execute(
            """
            SELECT last_winrate, last_kda, last_seen_at
            FROM bot_tracked_players
            WHERE telegram_id = %s AND player_id = %s
            """,
            (telegram_id, str(player_id)),
        )
        row = c.fetchone()
    return dict(row) if row else None


def update_last_seen(
    telegram_id: int,
    player_id: str,
    winrate: Optional[float],
    kda: Optional[float],
) -> None:
    with db_cursor(commit=True) as c:
        c.execute(
            """
            UPDATE bot_tracked_players
            SET last_winrate = %s,
                last_kda     = %s,
                last_seen_at = CURRENT_TIMESTAMP
            WHERE telegram_id = %s AND player_id = %s
            """,
            (winrate, kda, telegram_id, str(player_id)),
        )


def iter_users_with_notifications() -> List[int]:
    """Users that have notifications enabled AND have at least one tracked player."""
    with db_cursor() as c:
        c.execute(
            """
            SELECT DISTINCT t.telegram_id
            FROM bot_tracked_players t
            LEFT JOIN bot_user_prefs p ON p.telegram_id = t.telegram_id
            WHERE COALESCE(p.notifications, TRUE) = TRUE
            """
        )
        return [int(r["telegram_id"]) for r in c.fetchall()]
