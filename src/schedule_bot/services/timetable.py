"""Loading a user's effective timetable (weekly lessons + filtered dated lessons)."""

from __future__ import annotations

from typing import NamedTuple

from schedule_bot.db import Database
from schedule_bot.models import DatedLesson, Lesson
from schedule_bot.services.filters import apply_filters


class Timetable(NamedTuple):
    weekly: list[Lesson]
    dated: list[DatedLesson]


async def load_timetable(db: Database, user_id: int) -> Timetable:
    """Weekly lessons plus dated lessons with the user's parallel-group choices applied."""
    weekly = await db.list_lessons(user_id)
    dated = await db.list_dated_lessons(user_id)
    if dated:
        dated = apply_filters(dated, await db.get_filters(user_id))
    return Timetable(weekly, dated)
