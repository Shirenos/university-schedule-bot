from datetime import date

from conftest import SEMESTER_START, TZ, at, make_lesson
from schedule_bot.services.schedule import lessons_on, next_lesson, week_days

MON_ODD = date(2026, 9, 7)  # week 1 (odd)
MON_EVEN = date(2026, 9, 14)  # week 2 (even)


def test_lessons_on_filters_weekday_and_sorts():
    lessons = [
        make_lesson(0, "12:00", "13:30", subject="B"),
        make_lesson(0, "09:00", "10:30", subject="A"),
        make_lesson(1, "09:00", "10:30", subject="Tuesday"),
    ]
    result = lessons_on(lessons, MON_ODD, SEMESTER_START)
    assert [lesson.subject for lesson in result] == ["A", "B"]


def test_lessons_on_respects_parity():
    lessons = [
        make_lesson(0, subject="every"),
        make_lesson(0, "11:00", "12:30", subject="odd", parity="odd"),
        make_lesson(0, "13:00", "14:30", subject="even", parity="even"),
    ]
    odd = [lesson.subject for lesson in lessons_on(lessons, MON_ODD, SEMESTER_START)]
    even = [lesson.subject for lesson in lessons_on(lessons, MON_EVEN, SEMESTER_START)]
    assert odd == ["every", "odd"]
    assert even == ["every", "even"]


def test_week_days_starts_on_monday():
    days = week_days(date(2026, 9, 10))
    assert days[0] == MON_ODD
    assert days[-1] == date(2026, 9, 13)
    assert len(days) == 7


def test_next_lesson_later_today():
    lessons = [make_lesson(0, "09:00", "10:30", subject="A"), make_lesson(0, "12:00", "13:00")]
    start, lesson = next_lesson(lessons, at("2026-09-07", "10:00"), SEMESTER_START)
    assert lesson.start.hour == 12
    assert start == at("2026-09-07", "12:00")


def test_next_lesson_is_strictly_in_the_future():
    lessons = [make_lesson(0, "09:00", "10:30")]
    start, _ = next_lesson(lessons, at("2026-09-07", "09:00"), SEMESTER_START)
    assert start == at("2026-09-14", "09:00")  # the 09:00 class has already started


def test_next_lesson_rolls_over_to_next_week():
    lessons = [make_lesson(0, "09:00", "10:30")]
    start, _ = next_lesson(lessons, at("2026-09-07", "18:00"), SEMESTER_START)
    assert start == at("2026-09-14", "09:00")


def test_next_lesson_skips_wrong_parity_weeks():
    lessons = [make_lesson(2, "10:00", "11:30", parity="even")]
    # From Monday of odd week 1 the first even Wednesday is 2026-09-16.
    start, _ = next_lesson(lessons, at("2026-09-07", "08:00"), SEMESTER_START)
    assert start == at("2026-09-16", "10:00")


def test_next_lesson_odd_class_looks_two_weeks_ahead():
    lessons = [make_lesson(0, "09:00", "10:30", parity="odd")]
    start, _ = next_lesson(lessons, at("2026-09-07", "10:00"), SEMESTER_START)
    assert start == at("2026-09-21", "09:00")
    assert start.tzinfo == TZ


def test_next_lesson_none_when_empty():
    assert next_lesson([], at("2026-09-07", "10:00"), SEMESTER_START) is None
