from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from schedule_bot.db import Database
from schedule_bot.models import Lesson

TZ = ZoneInfo("Europe/Moscow")
# Monday, 2026-09-07 is the first day of week 1 (odd); week 2 (even) starts 2026-09-14.
SEMESTER_START = date(2026, 9, 7)


def make_lesson(
    weekday: int = 0,
    start: str = "09:00",
    end: str = "10:30",
    *,
    subject: str = "Math",
    type: str = "lecture",
    room: str = "101",
    teacher: str = "Ivanov",
    parity: str = "every",
    user_id: int = 1,
    id: int | None = None,
) -> Lesson:
    return Lesson(
        user_id=user_id,
        weekday=weekday,
        start=time.fromisoformat(start),
        end=time.fromisoformat(end),
        subject=subject,
        type=type,  # type: ignore[arg-type]
        room=room,
        teacher=teacher,
        parity=parity,  # type: ignore[arg-type]
        id=id,
    )


def at(day: str, clock: str = "00:00") -> datetime:
    return datetime.combine(date.fromisoformat(day), time.fromisoformat(clock), tzinfo=TZ)


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()
