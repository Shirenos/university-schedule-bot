"""Tolerant parsers for user-supplied values (used by the /add dialog and CSV import)."""

from __future__ import annotations

import re
from datetime import time

from schedule_bot.models import LessonType, Parity

WEEKDAY_ALIASES: dict[str, int] = {
    **{name: i for i, name in enumerate(["пн", "вт", "ср", "чт", "пт", "сб", "вс"])},
    **{name: i for i, name in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])},
    **{
        name: i
        for i, name in enumerate(
            [
                "понедельник",
                "вторник",
                "среда",
                "четверг",
                "пятница",
                "суббота",
                "воскресенье",
            ]
        )
    },
    **{
        name: i
        for i, name in enumerate(
            [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]
        )
    },
    "среду": 2,
    "пятницу": 4,
    "субботу": 5,
}

TYPE_ALIASES: dict[str, LessonType] = {
    "lecture": "lecture",
    "lec": "lecture",
    "лекция": "lecture",
    "лек": "lecture",
    "seminar": "seminar",
    "practice": "seminar",
    "семинар": "seminar",
    "сем": "seminar",
    "практика": "seminar",
    "практическое": "seminar",
    "lab": "lab",
    "laboratory": "lab",
    "лаб": "lab",
    "лабораторная": "lab",
    "лаба": "lab",
}

PARITY_ALIASES: dict[str, Parity] = {
    "every": "every",
    "all": "every",
    "each": "every",
    "каждая": "every",
    "каждую": "every",
    "все": "every",
    "odd": "odd",
    "нечётная": "odd",
    "нечетная": "odd",
    "нечёт": "odd",
    "нечет": "odd",
    "even": "even",
    "чётная": "even",
    "четная": "even",
    "чёт": "even",
    "чет": "even",
}

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")
_RANGE_RE = re.compile(r"^\s*(\d{1,2}[:.]\d{2})\s*[-–—]\s*(\d{1,2}[:.]\d{2})\s*$")


class ParseError(ValueError):
    """Raised when a value cannot be understood."""


def _norm(value: str) -> str:
    return value.strip().lower().rstrip(".")


def parse_weekday(value: str) -> int:
    """Accepts 1-7 (Mon=1), Russian or English names/abbreviations. Returns 0-6."""
    text = _norm(value)
    if text.isdigit():
        number = int(text)
        if 1 <= number <= 7:
            return number - 1
        raise ParseError(f"номер дня недели должен быть от 1 до 7: {value!r}")
    try:
        return WEEKDAY_ALIASES[text]
    except KeyError:
        raise ParseError(f"неизвестный день недели: {value!r}") from None


def parse_time(value: str) -> time:
    """Parse ``HH:MM`` (or ``HH.MM``)."""
    match = _TIME_RE.match(value)
    if not match:
        raise ParseError(f"неверное время (нужно ЧЧ:ММ): {value!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ParseError(f"неверное время (нужно ЧЧ:ММ): {value!r}")
    return time(hour, minute)


def parse_time_range(value: str) -> tuple[time, time]:
    """Parse ``HH:MM-HH:MM`` and make sure the class ends after it starts."""
    match = _RANGE_RE.match(value)
    if not match:
        raise ParseError(f"неверный интервал (нужно ЧЧ:ММ-ЧЧ:ММ): {value!r}")
    start, end = parse_time(match.group(1)), parse_time(match.group(2))
    ensure_ordered(start, end)
    return start, end


def ensure_ordered(start: time, end: time) -> None:
    if end <= start:
        raise ParseError("время окончания должно быть позже начала")


def parse_type(value: str) -> LessonType:
    try:
        return TYPE_ALIASES[_norm(value)]
    except KeyError:
        raise ParseError(f"неизвестный тип занятия: {value!r}") from None


def parse_parity(value: str) -> Parity:
    text = _norm(value)
    if not text:
        return "every"
    try:
        return PARITY_ALIASES[text]
    except KeyError:
        raise ParseError(f"неизвестная чётность недели: {value!r}") from None
