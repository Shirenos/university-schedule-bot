import asyncio
from datetime import datetime, timedelta

import pytest

from conftest import SEMESTER_START, TZ, at, make_lesson
from schedule_bot.services.reminders import ReminderScheduler, next_reminder


class FakeClock:
    """A controllable clock: sleeping just moves time forward."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


async def wait_until(predicate, timeout: float = 2.0) -> None:
    async def loop() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(loop(), timeout)


# --- next_reminder (pure) -------------------------------------------------------------------


def test_next_reminder_fires_minutes_before_start():
    lessons = [make_lesson(0, "09:00", "10:30")]
    fire_at, lesson, start = next_reminder(lessons, at("2026-09-07", "08:00"), 15, SEMESTER_START)
    assert fire_at == at("2026-09-07", "08:45")
    assert start == at("2026-09-07", "09:00")
    assert lesson is lessons[0]


def test_next_reminder_skips_moments_already_passed():
    lessons = [make_lesson(0, "09:00", "10:30")]
    # 08:50 is after the 08:45 reminder moment, so the next one is a week later.
    fire_at, _, _ = next_reminder(lessons, at("2026-09-07", "08:50"), 15, SEMESTER_START)
    assert fire_at == at("2026-09-14", "08:45")


def test_next_reminder_is_strictly_after_cursor():
    lessons = [make_lesson(0, "09:00", "10:30")]
    fire_at, _, _ = next_reminder(lessons, at("2026-09-07", "08:45"), 15, SEMESTER_START)
    assert fire_at == at("2026-09-14", "08:45")


def test_next_reminder_picks_earliest_of_several():
    lessons = [
        make_lesson(0, "14:00", "15:00", subject="late"),
        make_lesson(0, "11:00", "12:00", subject="early"),
    ]
    _, lesson, _ = next_reminder(lessons, at("2026-09-07", "07:00"), 15, SEMESTER_START)
    assert lesson.subject == "early"


def test_next_reminder_lead_time_crosses_midnight():
    lessons = [make_lesson(1, "00:10", "01:40")]
    fire_at, _, start = next_reminder(lessons, at("2026-09-07", "23:00"), 30, SEMESTER_START)
    assert fire_at == at("2026-09-07", "23:40")
    assert start == at("2026-09-08", "00:10")


def test_next_reminder_honours_parity():
    lessons = [make_lesson(0, "09:00", "10:30", parity="even")]
    fire_at, _, _ = next_reminder(lessons, at("2026-09-07", "07:00"), 15, SEMESTER_START)
    assert fire_at == at("2026-09-14", "08:45")


def test_next_reminder_none_without_lessons():
    assert next_reminder([], at("2026-09-07", "07:00"), 15, SEMESTER_START) is None


# --- ReminderScheduler -----------------------------------------------------------------------


def make_scheduler(db, clock, sent):
    async def send(user_id: int, text: str) -> None:
        sent.append((user_id, text, clock.now))

    return ReminderScheduler(db, send, TZ, SEMESTER_START, clock=clock, sleep=clock.sleep)


async def test_scheduler_sends_reminders_on_time(db):
    await db.add_lesson(make_lesson(0, "09:00", "10:30", subject="Матан", room="А-101"))
    await db.set_reminder(1, True, 15)
    clock = FakeClock(at("2026-09-06", "12:00"))
    sent: list = []
    scheduler = make_scheduler(db, clock, sent)

    scheduler.reschedule(1)
    await wait_until(lambda: len(sent) >= 2)
    await scheduler.stop()

    assert [when for _, _, when in sent[:2]] == [
        at("2026-09-07", "08:45"),
        at("2026-09-14", "08:45"),
    ]
    user_id, text, _ = sent[0]
    assert user_id == 1
    assert "Матан" in text and "15 мин" in text and "А-101" in text


async def test_scheduler_restores_enabled_users_from_sqlite(db):
    await db.add_lesson(make_lesson(user_id=1))
    await db.add_lesson(make_lesson(user_id=2))
    await db.set_reminder(1, True, 10)
    await db.set_reminder(2, False, 10)
    clock = FakeClock(at("2026-09-06", "12:00"))
    sent: list = []

    scheduler = make_scheduler(db, clock, sent)  # a "fresh process"
    await scheduler.start()
    await wait_until(lambda: len(sent) >= 1)
    await scheduler.stop()

    assert {user_id for user_id, _, _ in sent} == {1}
    assert "10 мин" in sent[0][1]


async def test_scheduler_does_nothing_for_disabled_or_empty_users(db):
    await db.add_lesson(make_lesson(user_id=1))
    await db.set_reminder(1, False, 15)
    await db.set_reminder(2, True, 15)  # enabled, but no lessons
    sent: list = []
    scheduler = make_scheduler(db, FakeClock(at("2026-09-06", "12:00")), sent)

    scheduler.reschedule(1)
    scheduler.reschedule(2)
    await wait_until(lambda: not scheduler.active_users)
    assert sent == []
    await scheduler.stop()


async def test_cancel_stops_pending_reminders(db):
    await db.add_lesson(make_lesson())
    await db.set_reminder(1, True, 15)
    sent: list = []
    blocker = asyncio.Event()

    async def blocked_sleep(_: float) -> None:
        await blocker.wait()

    scheduler = ReminderScheduler(
        db,
        lambda uid, text: asyncio.sleep(0),
        TZ,
        SEMESTER_START,
        clock=FakeClock(at("2026-09-06", "12:00")),
        sleep=blocked_sleep,
    )
    scheduler.reschedule(1)
    await wait_until(lambda: scheduler.active_users == {1})
    scheduler.cancel(1)
    await asyncio.sleep(0)
    assert scheduler.active_users == set()
    assert sent == []


async def test_send_failure_does_not_kill_the_loop(db):
    await db.add_lesson(make_lesson())
    await db.set_reminder(1, True, 15)
    clock = FakeClock(at("2026-09-06", "12:00"))
    calls: list[datetime] = []

    async def flaky_send(user_id: int, text: str) -> None:
        calls.append(clock.now)
        if len(calls) == 1:
            raise RuntimeError("telegram is down")

    scheduler = ReminderScheduler(
        db, flaky_send, TZ, SEMESTER_START, clock=clock, sleep=clock.sleep
    )
    scheduler.reschedule(1)
    await wait_until(lambda: len(calls) >= 2)
    await scheduler.stop()
    assert calls[1] - calls[0] == timedelta(days=7)


@pytest.mark.parametrize("minutes", [5, 60])
async def test_scheduler_uses_configured_lead_time(db, minutes):
    await db.add_lesson(make_lesson(0, "09:00", "10:30"))
    await db.set_reminder(1, True, minutes)
    clock = FakeClock(at("2026-09-06", "12:00"))
    sent: list = []
    scheduler = make_scheduler(db, clock, sent)
    scheduler.reschedule(1)
    await wait_until(lambda: len(sent) >= 1)
    await scheduler.stop()
    assert sent[0][2] == at("2026-09-07", "09:00") - timedelta(minutes=minutes)
