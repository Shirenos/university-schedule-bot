from datetime import date

import pytest

from schedule_bot.config import default_semester_start
from schedule_bot.services.parity import monday_of, parity_matches, week_number, week_parity

START = date(2026, 9, 1)  # Tuesday: week 1 starts on Monday 2026-08-31


def test_semester_start_week_is_odd_week_one():
    assert week_number(START, START) == 1
    assert week_parity(START, START) == "odd"


def test_monday_before_start_date_belongs_to_week_one():
    assert monday_of(START) == date(2026, 8, 31)
    assert week_number(date(2026, 8, 31), START) == 1


@pytest.mark.parametrize(
    ("day", "number", "parity"),
    [
        (date(2026, 9, 6), 1, "odd"),  # Sunday still week 1
        (date(2026, 9, 7), 2, "even"),  # next Monday flips parity
        (date(2026, 9, 13), 2, "even"),
        (date(2026, 9, 14), 3, "odd"),
        (date(2026, 12, 28), 18, "even"),
    ],
)
def test_week_number_and_parity(day, number, parity):
    assert week_number(day, START) == number
    assert week_parity(day, START) == parity


def test_dates_before_semester_continue_the_pattern():
    assert week_number(date(2026, 8, 30), START) == 0
    assert week_parity(date(2026, 8, 30), START) == "even"
    assert week_parity(date(2026, 8, 23), START) == "odd"


def test_year_boundary():
    assert week_parity(date(2026, 12, 28), START) == "even"  # week 18
    assert week_parity(date(2027, 1, 4), START) == "odd"  # week 19
    assert week_parity(date(2027, 1, 11), START) == "even"


@pytest.mark.parametrize(
    ("lesson", "current", "expected"),
    [
        ("every", "odd", True),
        ("every", "even", True),
        ("odd", "odd", True),
        ("odd", "even", False),
        ("even", "even", True),
        ("even", "odd", False),
    ],
)
def test_parity_matches(lesson, current, expected):
    assert parity_matches(lesson, current) is expected


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 3), date(2026, 9, 1)),
        (date(2026, 9, 1), date(2026, 9, 1)),
        (date(2026, 8, 31), date(2025, 9, 1)),
        (date(2027, 2, 10), date(2026, 9, 1)),
    ],
)
def test_default_semester_start(today, expected):
    assert default_semester_start(today) == expected
