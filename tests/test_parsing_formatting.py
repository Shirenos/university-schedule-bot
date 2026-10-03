from datetime import date, time

import pytest

from conftest import SEMESTER_START, at, make_lesson
from schedule_bot.services import formatting
from schedule_bot.services.parsing import (
    ParseError,
    parse_parity,
    parse_time,
    parse_time_range,
    parse_type,
    parse_weekday,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", 0),
        ("7", 6),
        ("Пн", 0),
        ("понедельник", 0),
        ("среду", 2),
        ("Fri", 4),
        ("sunday", 6),
        ("сб.", 5),
    ],
)
def test_parse_weekday(value, expected):
    assert parse_weekday(value) == expected


@pytest.mark.parametrize("value", ["0", "8", "funday", ""])
def test_parse_weekday_invalid(value):
    with pytest.raises(ParseError):
        parse_weekday(value)


def test_parse_time_and_range():
    assert parse_time("9:05") == time(9, 5)
    assert parse_time("09.05") == time(9, 5)
    assert parse_time_range("09:00 - 10:30") == (time(9, 0), time(10, 30))
    assert parse_time_range("09:00–10:30") == (time(9, 0), time(10, 30))


@pytest.mark.parametrize("value", ["24:00", "9:60", "abc", "9", "10:30-09:00", "09:00-09:00"])
def test_parse_time_range_invalid(value):
    with pytest.raises(ParseError):
        parse_time_range(value)


def test_parse_type_and_parity():
    assert parse_type("Семинар") == "seminar"
    assert parse_type("lab") == "lab"
    assert parse_parity("") == "every"
    assert parse_parity("Нечётная") == "odd"
    with pytest.raises(ParseError):
        parse_type("exam")
    with pytest.raises(ParseError):
        parse_parity("sometimes")


def test_format_lesson_escapes_html():
    text = formatting.format_lesson(make_lesson(subject="<b>hack</b> & co", teacher="O'Neil <x>"))
    assert "<b>hack" not in text
    assert "&lt;b&gt;hack&lt;/b&gt; &amp; co" in text
    assert "&lt;x&gt;" in text


def test_format_day_empty_and_filled():
    day = date(2026, 9, 7)
    assert "Занятий нет" in formatting.format_day("Сегодня", day, [], SEMESTER_START)
    text = formatting.format_day("Сегодня", day, [make_lesson(subject="Матан")], SEMESTER_START)
    assert "Матан" in text and "нечётная неделя" in text and "понедельник" in text


def test_format_week_skips_empty_days_and_marks_today():
    lessons = [make_lesson(0, subject="Mon"), make_lesson(3, subject="Thu")]
    text = formatting.format_week(date(2026, 9, 9), lessons, SEMESTER_START)
    assert "Mon" in text and "Thu" in text
    assert "Вторник" not in text
    assert "сегодня" not in text  # Wednesday has no classes, so it is not listed
    assert "👈 сегодня" in formatting.format_week(date(2026, 9, 7), lessons, SEMESTER_START)


def test_format_next_countdown():
    lesson = make_lesson(0, "09:00", "10:30")
    text = formatting.format_next(at("2026-09-07", "09:00"), lesson, at("2026-09-07", "07:45"))
    assert "Сегодня" in text and "1 ч 15 мин" in text
    later = formatting.format_next(at("2026-09-09", "09:00"), lesson, at("2026-09-07", "09:00"))
    assert "Среда" in later and "2 д" in later


def test_format_week_parity():
    text = formatting.format_week_parity(date(2026, 9, 14), SEMESTER_START)
    assert "чётная" in text and "№2" in text
    assert "ещё не начался" in formatting.format_week_parity(date(2026, 8, 1), SEMESTER_START)


def test_format_lesson_list_shows_ids_and_parity():
    lessons = [make_lesson(0, id=5, parity="odd"), make_lesson(4, id=6)]
    text = formatting.format_lesson_list(lessons)
    assert "#5" in text and "#6" in text and "нечётные недели" in text
    assert "пусто" in formatting.format_lesson_list([])


def test_split_message_respects_limit():
    text = "\n".join(f"line {i}" for i in range(1000))
    chunks = formatting.split_message(text, limit=200)
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "\n".join(chunks) == text
    assert formatting.split_message("short") == ["short"]
