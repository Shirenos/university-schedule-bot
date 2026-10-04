"""Plain data structures shared across the application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

LessonType = Literal["lecture", "seminar", "lab"]
Parity = Literal["every", "odd", "even"]

LESSON_TYPES: tuple[LessonType, ...] = ("lecture", "seminar", "lab")
PARITIES: tuple[Parity, ...] = ("every", "odd", "even")

DEFAULT_REMIND_MINUTES = 15
MAX_REMIND_MINUTES = 24 * 60
MAX_LESSONS_PER_USER = 200


@dataclass(frozen=True, slots=True)
class Lesson:
    """A single recurring class in a user's weekly schedule.

    ``weekday`` follows :meth:`datetime.date.weekday` (0 = Monday ... 6 = Sunday).
    """

    user_id: int
    weekday: int
    start: time
    end: time
    subject: str
    type: LessonType = "lecture"
    room: str = ""
    teacher: str = ""
    parity: Parity = "every"
    id: int | None = None
    label: str = ""  # optional display name of the lesson type, e.g. "практика"


@dataclass(frozen=True, slots=True)
class ReminderSettings:
    """Per-user reminder preferences."""

    enabled: bool = False
    minutes: int = DEFAULT_REMIND_MINUTES


@dataclass(frozen=True, slots=True)
class DatedLesson:
    """A class on a specific calendar date (e.g. synced from the university website).

    ``kind`` is the raw lesson kind as published (``"Практические занятия (фр)"``);
    ``type`` is the normalised :data:`LessonType` used for display.
    """

    user_id: int
    date: date
    start: time
    end: time
    subject: str
    kind: str = ""
    type: LessonType = "seminar"
    room: str = ""
    teacher: str = ""
    group: str = ""
    id: int | None = None


@dataclass(frozen=True, slots=True)
class TulguSettings:
    """Per-user ТулГУ sync state."""

    group: str
    synced_at: datetime | None = None
    min_date: date | None = None
    max_date: date | None = None
