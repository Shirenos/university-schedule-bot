"""Merging dated (university) lessons with weekly ones: views, next class and reminders."""

from datetime import date, timedelta

from conftest import SEMESTER_START, TZ, at, make_dated, make_lesson
from schedule_bot.services import formatting
from schedule_bot.services.filters import apply_filters
from schedule_bot.services.reminders import ReminderScheduler, next_reminder
from schedule_bot.services.schedule import dated_as_lesson, lessons_on, next_lesson
from schedule_bot.services.timetable import load_timetable

WED = date(2026, 9, 9)  # Wednesday of week 1 (odd)


def test_dated_lessons_appear_only_on_their_date():
    dated = [make_dated(WED, subject="Algebra")]
    assert [x.subject for x in lessons_on([], WED, SEMESTER_START, dated)] == ["Algebra"]
    assert lessons_on([], WED + timedelta(days=7), SEMESTER_START, dated) == []


def test_merge_sorts_weekly_and_dated_together():
    weekly = [make_lesson(2, "13:00", "14:30", subject="Weekly")]
    dated = [make_dated(WED, "09:00", "10:30", subject="Dated")]
    merged = lessons_on(weekly, WED, SEMESTER_START, dated)
    assert [x.subject for x in merged] == ["Dated", "Weekly"]


def test_duplicates_are_removed_dated_wins():
    weekly = [make_lesson(2, "09:00", "10:30", subject="  algebra  ", room="old", id=3)]
    dated = [make_dated(WED, "09:00", "10:30", subject="Algebra", room="new")]
    [lesson] = lessons_on(weekly, WED, SEMESTER_START, dated)
    assert lesson.room == "new"
    assert lesson.id is None


def test_same_time_different_subject_is_not_a_duplicate():
    weekly = [make_lesson(2, "09:00", "10:30", subject="Chess club")]
    dated = [make_dated(WED, "09:00", "10:30", subject="Algebra")]
    assert len(lessons_on(weekly, WED, SEMESTER_START, dated)) == 2


def test_weekly_parity_still_applies_when_merging():
    weekly = [make_lesson(2, "15:00", "16:00", subject="odd only", parity="odd")]
    even_wed = WED + timedelta(days=7)
    dated = [make_dated(WED, "09:00", "10:30"), make_dated(even_wed, "09:00", "10:30")]
    assert len(lessons_on(weekly, WED, SEMESTER_START, dated)) == 2  # odd week: both
    assert len(lessons_on(weekly, even_wed, SEMESTER_START, dated)) == 1  # even week: dated only


def test_dated_as_lesson_keeps_parallel_suffix_in_title():
    lesson = dated_as_lesson(make_dated(WED, subject="Язык", kind="Практические занятия (фр)"))
    assert lesson.subject == "Язык (фр)"
    assert lesson.weekday == 2 and lesson.parity == "every"
    assert dated_as_lesson(make_dated(WED, subject="Язык")).subject == "Язык"


def test_views_use_real_dates():
    dated = [make_dated(WED, subject="Algebra")]
    day = formatting.format_day(WED, [], SEMESTER_START, dated)
    assert "Algebra" in day and "Занятий нет" not in day
    next_day = formatting.format_day(WED + timedelta(days=1), [], SEMESTER_START, dated)
    assert "Занятий нет" in next_day
    week = formatting.format_week(WED, [], SEMESTER_START, dated)
    assert "Algebra" in week and "сегодня" in week
    assert "Algebra" not in formatting.format_week(
        WED + timedelta(days=7), [], SEMESTER_START, dated
    )


def test_next_lesson_considers_dated_and_weekly():
    weekly = [make_lesson(4, "09:00", "10:30", subject="Friday weekly")]  # Fri 2026-09-11
    dated = [make_dated(WED, "14:00", "15:30", subject="Wed dated")]
    start, lesson = next_lesson(weekly, at("2026-09-09", "08:00"), SEMESTER_START, dated)
    assert lesson.subject == "Wed dated" and start == at("2026-09-09", "14:00")
    start, lesson = next_lesson(weekly, at("2026-09-09", "16:00"), SEMESTER_START, dated)
    assert lesson.subject == "Friday weekly"


def test_next_lesson_finds_dated_lesson_after_a_long_break():
    dated = [make_dated(date(2027, 1, 11), "09:40", "11:15", subject="After holidays")]
    start, lesson = next_lesson([], at("2026-12-28", "10:00"), SEMESTER_START, dated)
    assert lesson.subject == "After holidays"
    assert start == at("2027-01-11", "09:40")


def test_next_lesson_none_after_last_dated_lesson():
    dated = [make_dated(WED)]
    assert next_lesson([], at("2026-09-10", "10:00"), SEMESTER_START, dated) is None


def test_next_reminder_for_dated_lessons():
    dated = [make_dated(WED, "07:45", "09:20", subject="Early")]
    fire_at, lesson, start = next_reminder([], at("2026-09-08", "20:00"), 15, SEMESTER_START, dated)
    assert (fire_at, start) == (at("2026-09-09", "07:30"), at("2026-09-09", "07:45"))
    assert lesson.subject == "Early"


def test_next_reminder_dated_after_long_gap_and_dedupe():
    dated = [make_dated(date(2027, 1, 11), "09:40", "11:15")]
    fire_at, _, _ = next_reminder([], at("2026-12-28", "10:00"), 15, SEMESTER_START, dated)
    assert fire_at == at("2027-01-11", "09:25")

    weekly = [make_lesson(2, "09:00", "10:30", subject="Math")]
    same = [make_dated(WED, "09:00", "10:30", subject="Math")]
    first = next_reminder(weekly, at("2026-09-09", "08:00"), 15, SEMESTER_START, same)
    second = next_reminder(weekly, first[0], 15, SEMESTER_START, same)
    assert first[0] == at("2026-09-09", "08:45")
    assert second[0] == at("2026-09-16", "08:45")  # next weekly occurrence, not a double reminder


async def test_load_timetable_applies_filters(db):
    dated = [
        make_dated(WED, "07:45", "09:20", subject="Язык", kind="Практические занятия (фр)"),
        make_dated(WED, "07:45", "09:20", subject="Язык", kind="Практические занятия (нем)"),
    ]
    await db.replace_dated_lessons(1, dated)
    _, everything = await load_timetable(db, 1)
    assert len(everything) == 2
    await db.set_filter(1, "Язык", "Практические занятия", "нем")
    _, filtered = await load_timetable(db, 1)
    assert [x.kind for x in filtered] == ["Практические занятия (нем)"]
    assert (
        apply_filters(dated, {("Язык", "Практические занятия"): "нем"})[0].kind == filtered[0].kind
    )


async def test_scheduler_reminds_about_dated_lessons_respecting_filters(db):
    from test_reminders import FakeClock, wait_until

    await db.replace_dated_lessons(
        1,
        [
            make_dated(WED, "07:45", "09:20", subject="Язык", kind="Практические занятия (фр)"),
            make_dated(WED, "07:45", "09:20", subject="Язык", kind="Практические занятия (нем)"),
        ],
    )
    await db.set_filter(1, "Язык", "Практические занятия", "фр")
    await db.set_reminder(1, True, 15)
    clock = FakeClock(at("2026-09-08", "20:00"))
    sent: list = []

    async def send(user_id: int, text: str) -> None:
        sent.append((user_id, text, clock.now))

    scheduler = ReminderScheduler(db, send, TZ, SEMESTER_START, clock=clock, sleep=clock.sleep)
    await scheduler.start()  # restored from SQLite: dated-only user, no weekly lessons
    await wait_until(lambda: len(sent) >= 1)
    await asyncio_sleep_a_bit()
    await scheduler.stop()

    assert len(sent) == 1  # one reminder for the chosen subgroup, nothing for (нем)
    assert sent[0][2] == at("2026-09-09", "07:30")
    assert "Язык (фр)" in sent[0][1]


async def asyncio_sleep_a_bit() -> None:
    import asyncio

    for _ in range(20):
        await asyncio.sleep(0)
