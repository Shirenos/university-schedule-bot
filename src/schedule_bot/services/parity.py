"""Odd/even week arithmetic.

Week 1 is the Monday-to-Sunday week that contains the semester start date, so
weeks 1, 3, 5... are *odd* and weeks 2, 4, 6... are *even*. Dates before the
semester start extend the same pattern backwards (week 0 is even, -1 is odd, ...).
"""

from __future__ import annotations

from datetime import date, timedelta

from schedule_bot.models import Parity


def monday_of(day: date) -> date:
    """Monday of the week containing ``day``."""
    return day - timedelta(days=day.weekday())


def week_number(day: date, semester_start: date) -> int:
    """1-based number of the semester week containing ``day`` (may be <= 0 before the start)."""
    return (monday_of(day) - monday_of(semester_start)).days // 7 + 1


def week_parity(day: date, semester_start: date) -> Parity:
    """``"odd"`` or ``"even"`` for the week containing ``day``."""
    return "odd" if week_number(day, semester_start) % 2 else "even"


def parity_matches(lesson_parity: Parity, current: Parity) -> bool:
    """Whether a lesson with ``lesson_parity`` takes place in a week of parity ``current``."""
    return lesson_parity == "every" or lesson_parity == current
