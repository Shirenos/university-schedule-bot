"""Pure schedule logic: which lessons happen when, and what comes next.

Two sources feed the timetable: *weekly* lessons (recurring, with odd/even parity, added by
hand or via CSV) and *dated* lessons (concrete calendar dates, e.g. synced from the university
site). For any given day both are merged, with dated lessons winning over weekly duplicates.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta, tzinfo

from schedule_bot.models import DatedLesson, Lesson
from schedule_bot.services.filters import split_kind
from schedule_bot.services.parity import monday_of, parity_matches, week_parity

# Parity repeats every two weeks, so two weeks of lookahead always finds the next weekly class.
LOOKAHEAD_DAYS = 14
# Dated lessons can start after a long break (e.g. winter holidays); never look further than this.
MAX_LOOKAHEAD_DAYS = 400


def _norm(subject: str) -> str:
    return " ".join(subject.casefold().split())


def dated_as_lesson(dated: DatedLesson) -> Lesson:
    """Display form of a dated lesson (the parallel-group suffix is kept in the title)."""
    base, suffix = split_kind(dated.kind)
    subject = f"{dated.subject} ({suffix})" if suffix else dated.subject
    return Lesson(
        user_id=dated.user_id,
        weekday=dated.date.weekday(),
        start=dated.start,
        end=dated.end,
        subject=subject,
        type=dated.type,
        room=dated.room,
        teacher=dated.teacher,
        parity="every",
        id=None,
        label="практика" if base.lower().startswith("практ") else "",
    )


def lessons_on(
    lessons: Iterable[Lesson],
    day: date,
    semester_start: date,
    dated: Iterable[DatedLesson] = (),
) -> list[Lesson]:
    """Lessons that take place on ``day``, merged and sorted by start time.

    Weekly lessons are matched by weekday and week parity. A weekly lesson with the same time
    slot and subject as a dated one is considered a duplicate and dropped in favour of the
    dated lesson.
    """
    parity = week_parity(day, semester_start)
    weekly = [
        lesson
        for lesson in lessons
        if lesson.weekday == day.weekday() and parity_matches(lesson.parity, parity)
    ]
    todays_dated = [d for d in dated if d.date == day]
    if todays_dated:
        taken = {(d.start, d.end, _norm(d.subject)) for d in todays_dated}
        weekly = [w for w in weekly if (w.start, w.end, _norm(w.subject)) not in taken]
    merged = weekly + [dated_as_lesson(d) for d in todays_dated]
    return sorted(merged, key=lambda lesson: (lesson.start, lesson.end, lesson.id or 0))


def week_days(day: date) -> list[date]:
    """The seven dates (Monday first) of the week containing ``day``."""
    monday = monday_of(day)
    return [monday + timedelta(days=i) for i in range(7)]


def start_datetime(lesson: Lesson, day: date, tz: tzinfo) -> datetime:
    return datetime.combine(day, lesson.start, tzinfo=tz)


def lookahead_days(since: date, dated: Iterable[DatedLesson], minimum: int = LOOKAHEAD_DAYS) -> int:
    """Days to scan: at least ``minimum``, extended to reach the last dated lesson."""
    last = max((d.date for d in dated), default=None)
    if last is None:
        return minimum
    return max(minimum, min(MAX_LOOKAHEAD_DAYS, (last - since).days + 1))


def iter_occurrences(
    lessons: Iterable[Lesson],
    since: date,
    semester_start: date,
    tz: tzinfo,
    days: int | None = None,
    dated: Iterable[DatedLesson] = (),
) -> Iterator[tuple[datetime, Lesson]]:
    """Lazily yield ``(start, lesson)`` in chronological order, beginning at ``since``.

    By default the scan covers two weeks, extended so that every dated lesson is reachable.
    """
    lessons = list(lessons)
    dated = list(dated)
    span = days if days is not None else lookahead_days(since, dated)
    for offset in range(span + 1):
        day = since + timedelta(days=offset)
        for lesson in lessons_on(lessons, day, semester_start, dated):
            yield start_datetime(lesson, day, tz), lesson


def next_lesson(
    lessons: Iterable[Lesson],
    now: datetime,
    semester_start: date,
    dated: Iterable[DatedLesson] = (),
) -> tuple[datetime, Lesson] | None:
    """The first class that starts strictly after ``now``, or ``None`` if there is none."""
    tz = now.tzinfo
    assert tz is not None, "now must be timezone-aware"
    for start, lesson in iter_occurrences(lessons, now.date(), semester_start, tz, dated=dated):
        if start > now:
            return start, lesson
    return None
