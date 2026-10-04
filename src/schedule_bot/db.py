"""SQLite storage layer (aiosqlite). The only module that speaks SQL."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime, time
from pathlib import Path

import aiosqlite

from schedule_bot.models import (
    DEFAULT_REMIND_MINUTES,
    DatedLesson,
    Lesson,
    ReminderSettings,
    TulguSettings,
)

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

CREATE TABLE IF NOT EXISTS dated_lessons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    date        TEXT    NOT NULL,
    start       TEXT    NOT NULL,
    end         TEXT    NOT NULL,
    subject     TEXT    NOT NULL,
    kind        TEXT    NOT NULL DEFAULT '',
    type        TEXT    NOT NULL CHECK (type IN ('lecture', 'seminar', 'lab')),
    room        TEXT    NOT NULL DEFAULT '',
    teacher     TEXT    NOT NULL DEFAULT '',
    group_name  TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_dated_user_date ON dated_lessons (user_id, date, start);

CREATE TABLE IF NOT EXISTS tulgu_settings (
    user_id    INTEGER PRIMARY KEY,
    group_code TEXT NOT NULL,
    synced_at  TEXT,
    min_date   TEXT,
    max_date   TEXT
);

CREATE TABLE IF NOT EXISTS lesson_filters (
    user_id  INTEGER NOT NULL,
    subject  TEXT    NOT NULL,
    kind     TEXT    NOT NULL,
    choice   TEXT    NOT NULL,
    PRIMARY KEY (user_id, subject, kind)
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


def _row_to_dated(row: sqlite3.Row) -> DatedLesson:
    return DatedLesson(
        id=row["id"],
        user_id=row["user_id"],
        date=date.fromisoformat(row["date"]),
        start=time.fromisoformat(row["start"]),
        end=time.fromisoformat(row["end"]),
        subject=row["subject"],
        kind=row["kind"],
        type=row["type"],
        room=row["room"],
        teacher=row["teacher"],
        group=row["group_name"],
    )


def _opt_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


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

    # --- dated lessons (university sync) -----------------------------------------------------

    async def replace_dated_lessons(self, user_id: int, lessons: Iterable[DatedLesson]) -> int:
        """Atomically replace all of the user's dated lessons; returns how many were stored."""
        params = [
            (
                user_id,
                lesson.date.isoformat(),
                lesson.start.strftime("%H:%M"),
                lesson.end.strftime("%H:%M"),
                lesson.subject,
                lesson.kind,
                lesson.type,
                lesson.room,
                lesson.teacher,
                lesson.group,
            )
            for lesson in lessons
        ]
        try:
            await self.conn.execute("DELETE FROM dated_lessons WHERE user_id = ?", (user_id,))
            await self.conn.executemany(
                "INSERT INTO dated_lessons "
                "(user_id, date, start, end, subject, kind, type, room, teacher, group_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                params,
            )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
        return len(params)

    async def list_dated_lessons(self, user_id: int) -> list[DatedLesson]:
        cur = await self.conn.execute(
            "SELECT * FROM dated_lessons WHERE user_id = ? ORDER BY date, start, id", (user_id,)
        )
        return [_row_to_dated(row) for row in await cur.fetchall()]

    async def count_dated_lessons(self, user_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM dated_lessons WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def clear_dated_lessons(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM dated_lessons WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    # --- TulSU settings ----------------------------------------------------------------------

    async def get_tulgu(self, user_id: int) -> TulguSettings | None:
        cur = await self.conn.execute("SELECT * FROM tulgu_settings WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        return TulguSettings(
            group=row["group_code"],
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
            min_date=_opt_date(row["min_date"]),
            max_date=_opt_date(row["max_date"]),
        )

    async def set_tulgu(self, user_id: int, settings: TulguSettings) -> None:
        await self.conn.execute(
            "INSERT INTO tulgu_settings (user_id, group_code, synced_at, min_date, max_date) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "group_code = excluded.group_code, synced_at = excluded.synced_at, "
            "min_date = excluded.min_date, max_date = excluded.max_date",
            (
                user_id,
                settings.group,
                settings.synced_at.isoformat() if settings.synced_at else None,
                settings.min_date.isoformat() if settings.min_date else None,
                settings.max_date.isoformat() if settings.max_date else None,
            ),
        )
        await self.conn.commit()

    # --- parallel-subgroup filters -----------------------------------------------------------

    async def get_filters(self, user_id: int) -> dict[tuple[str, str], str]:
        """Choices as ``{(subject, kind_base): choice}``; ``"*"`` means "show all variants"."""
        cur = await self.conn.execute(
            "SELECT subject, kind, choice FROM lesson_filters WHERE user_id = ?", (user_id,)
        )
        return {(row["subject"], row["kind"]): row["choice"] for row in await cur.fetchall()}

    async def set_filter(self, user_id: int, subject: str, kind: str, choice: str) -> None:
        await self.conn.execute(
            "INSERT INTO lesson_filters (user_id, subject, kind, choice) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, subject, kind) DO UPDATE SET choice = excluded.choice",
            (user_id, subject, kind, choice),
        )
        await self.conn.commit()

    async def clear_filters(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM lesson_filters WHERE user_id = ?", (user_id,))
        await self.conn.commit()
