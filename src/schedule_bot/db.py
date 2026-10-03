"""SQLite storage layer (aiosqlite). The only module that speaks SQL."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import time
from pathlib import Path

import aiosqlite

from schedule_bot.models import DEFAULT_REMIND_MINUTES, Lesson, ReminderSettings

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    weekday  INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start    TEXT    NOT NULL,
    end      TEXT    NOT NULL,
    subject  TEXT    NOT NULL,
    type     TEXT    NOT NULL CHECK (type IN ('lecture', 'seminar', 'lab')),
    room     TEXT    NOT NULL DEFAULT '',
    teacher  TEXT    NOT NULL DEFAULT '',
    parity   TEXT    NOT NULL DEFAULT 'every' CHECK (parity IN ('every', 'odd', 'even'))
);
CREATE INDEX IF NOT EXISTS idx_lessons_user ON lessons (user_id, weekday, start);

CREATE TABLE IF NOT EXISTS reminders (
    user_id  INTEGER PRIMARY KEY,
    enabled  INTEGER NOT NULL DEFAULT 0,
    minutes  INTEGER NOT NULL DEFAULT 15
);
"""


def _row_to_lesson(row: sqlite3.Row) -> Lesson:
    return Lesson(
        id=row["id"],
        user_id=row["user_id"],
        weekday=row["weekday"],
        start=time.fromisoformat(row["start"]),
        end=time.fromisoformat(row["end"]),
        subject=row["subject"],
        type=row["type"],
        room=row["room"],
        teacher=row["teacher"],
        parity=row["parity"],
    )


def _lesson_params(lesson: Lesson) -> tuple[object, ...]:
    return (
        lesson.user_id,
        lesson.weekday,
        lesson.start.strftime("%H:%M"),
        lesson.end.strftime("%H:%M"),
        lesson.subject,
        lesson.type,
        lesson.room,
        lesson.teacher,
        lesson.parity,
    )


_INSERT_LESSON = (
    "INSERT INTO lessons (user_id, weekday, start, end, subject, type, room, teacher, parity) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


class Database:
    """Thin async repository around a single SQLite connection."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected; call connect() first")
        return self._conn

    async def connect(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # --- lessons -----------------------------------------------------------------------------

    async def add_lesson(self, lesson: Lesson) -> int:
        cur = await self.conn.execute(_INSERT_LESSON, _lesson_params(lesson))
        await self.conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def add_lessons(self, lessons: Iterable[Lesson]) -> int:
        """Insert many lessons in one transaction; returns how many were stored."""
        params = [_lesson_params(lesson) for lesson in lessons]
        await self.conn.executemany(_INSERT_LESSON, params)
        await self.conn.commit()
        return len(params)

    async def list_lessons(self, user_id: int) -> list[Lesson]:
        cur = await self.conn.execute(
            "SELECT * FROM lessons WHERE user_id = ? ORDER BY weekday, start, id", (user_id,)
        )
        return [_row_to_lesson(row) for row in await cur.fetchall()]

    async def count_lessons(self, user_id: int) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM lessons WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def delete_lesson(self, user_id: int, lesson_id: int) -> bool:
        """Delete a lesson owned by ``user_id``. Returns False if it does not exist."""
        cur = await self.conn.execute(
            "DELETE FROM lessons WHERE id = ? AND user_id = ?", (lesson_id, user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # --- reminders ---------------------------------------------------------------------------

    async def get_reminder(self, user_id: int) -> ReminderSettings:
        cur = await self.conn.execute(
            "SELECT enabled, minutes FROM reminders WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return ReminderSettings(enabled=False, minutes=DEFAULT_REMIND_MINUTES)
        return ReminderSettings(enabled=bool(row["enabled"]), minutes=row["minutes"])

    async def set_reminder(self, user_id: int, enabled: bool, minutes: int) -> None:
        await self.conn.execute(
            "INSERT INTO reminders (user_id, enabled, minutes) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET enabled = excluded.enabled, "
            "minutes = excluded.minutes",
            (user_id, int(enabled), minutes),
        )
        await self.conn.commit()

    async def list_reminder_users(self) -> list[int]:
        """User ids with reminders enabled (used to restore the scheduler at startup)."""
        cur = await self.conn.execute("SELECT user_id FROM reminders WHERE enabled = 1")
        return [row["user_id"] for row in await cur.fetchall()]
