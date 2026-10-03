"""Pure schedule logic: which lessons happen when, and what comes next."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta, tzinfo

from schedule_bot.models import Lesson
from schedule_bot.services.parity import monday_of, parity_matches, week_parity

# Parity repeats every two weeks, so two weeks of lookahead always finds the next class.
LOOKAHEAD_DAYS = 14


def lessons_on(lessons: Iterable[Lesson], day: date, semester_start: date) -> list[Lesson]:
    """Lessons that take place on ``day`` (weekday and week parity considered), by start time."""
    parity = week_parity(day, semester_start)
    matching = [
        lesson
        for lesson in lessons
        if lesson.weekday == day.weekday() and parity_matches(lesson.parity, parity)
    ]
    return sorted(matching, key=lambda lesson: (lesson.start, lesson.end, lesson.id or 0))


def week_days(day: date) -> list[date]:
    """The seven dates (Monday first) of the week containing ``day``."""
    monday = monday_of(day)
    return [monday + timedelta(days=i) for i in range(7)]


def start_datetime(lesson: Lesson, day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, lesson.start, tzinfo=tz)


def iter_occurrences(
    lessons: Iterable[Lesson],
    since: date,
    semester_start: date,
    tz: tzinfo,
    days: int = LOOKAHEAD_DAYS,
) -> Iterator[tuple[datetime, Lesson]]:
    """Yield ``(start, lesson)`` for every occurrence from ``since`` over ``days`` days."""
    lessons = list(lessons)
    for offset in range(days + 1):
        day = since + timedelta(days=offset)
        for lesson in lessons_on(lessons, day, semester_start):
            yield start_datetime(lesson, day, tz), lesson


def next_lesson(
    lessons: Iterable[Lesson], now: datetime, semester_start: date
) -> tuple[datetime, Lesson] | None:
    """The first class that starts strictly after ``now``, or ``None`` if there is none."""
    tz = now.tzinfo
    assert tz is not None, "now must be timezone-aware"
    for start, lesson in iter_occurrences(lessons, now.date(), semester_start, tz):
        if start > now:
            return start, lesson
    return None
