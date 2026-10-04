"""Reminder scheduling: pure "what fires next" logic plus an asyncio scheduler.

The scheduler keeps one asyncio task per user. Each task sleeps until the next
reminder moment, sends the message and repeats. All durable state (enabled flag,
minutes, lessons) lives in SQLite, so :meth:`ReminderScheduler.start` simply
re-creates the tasks for every user with reminders enabled.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import date, datetime, timedelta, tzinfo

from schedule_bot.db import Database
from schedule_bot.models import DatedLesson, Lesson
from schedule_bot.services.formatting import format_reminder
from schedule_bot.services.schedule import iter_occurrences
from schedule_bot.services.timetable import load_timetable

logger = logging.getLogger(__name__)

SendFunc = Callable[[int, str], Awaitable[object]]
SleepFunc = Callable[[float], Awaitable[None]]
ClockFunc = Callable[[], datetime]


def next_reminder(
    lessons: Iterable[Lesson],
    after: datetime,
    minutes: int,
    semester_start: date,
    dated: Iterable[DatedLesson] = (),
) -> tuple[datetime, Lesson, datetime] | None:
    """Find the next reminder strictly after ``after``.

    Weekly and dated lessons are merged the same way as in the schedule views. Returns
    ``(fire_at, lesson, lesson_start)`` or ``None`` when nothing is left to remind about.
    """
    tz = after.tzinfo
    assert tz is not None, "after must be timezone-aware"
    lead = timedelta(minutes=minutes)
    # Start one day early: a class tomorrow at 00:10 with a 30 minute lead fires today.
    since = after.date() - timedelta(days=1)
    # Occurrences come in chronological order, so the first one in the future is the earliest.
    for start, lesson in iter_occurrences(lessons, since, semester_start, tz, dated=dated):
        if start - lead > after:
            return start - lead, lesson, start
    return None


class ReminderScheduler:
    """Sends "class starts in N minutes" messages to users who enabled reminders."""

    def __init__(
        self,
        db: Database,
        send: SendFunc,
        timezone: tzinfo,
        semester_start: date,
        *,
        clock: ClockFunc | None = None,
        sleep: SleepFunc = asyncio.sleep,
    ) -> None:
        self._db = db
        self._send = send
        self._tz = timezone
        self._semester_start = semester_start
        self._clock = clock or (lambda: datetime.now(timezone))
        self._sleep = sleep
        self._tasks: dict[int, asyncio.Task[None]] = {}

    @property
    def active_users(self) -> set[int]:
        return {uid for uid, task in self._tasks.items() if not task.done()}

    async def start(self) -> None:
        """Restore reminder tasks from SQLite (call once at startup)."""
        user_ids = await self._db.list_reminder_users()
        for user_id in user_ids:
            self.reschedule(user_id)
        logger.info("Restored reminders for %d user(s)", len(user_ids))

    def reschedule(self, user_id: int) -> None:
        """(Re)start the user's task; call after reminder settings or the schedule change."""
        self.cancel(user_id)
        self._tasks[user_id] = asyncio.create_task(self._run(user_id), name=f"reminders-{user_id}")

    def cancel(self, user_id: int) -> None:
        task = self._tasks.pop(user_id, None)
        if task is not None:
            task.cancel()

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self, user_id: int) -> None:
        cursor = self._clock()
        while True:
            settings = await self._db.get_reminder(user_id)
            if not settings.enabled:
                return
            weekly, dated = await load_timetable(self._db, user_id)
            upcoming = next_reminder(weekly, cursor, settings.minutes, self._semester_start, dated)
            if upcoming is None:
                return  # nothing to remind about; /add or /import will reschedule
            fire_at, lesson, _start = upcoming
            delay = (fire_at - self._clock()).total_seconds()
            if delay > 0:
                await self._sleep(delay)
            cursor = fire_at
            try:
                await self._send(user_id, format_reminder(lesson, settings.minutes))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to send reminder to user %s", user_id)
