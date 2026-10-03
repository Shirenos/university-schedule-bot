"""Render schedule data as Telegram HTML messages (Russian UI)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from html import escape

from schedule_bot.models import Lesson, Parity
from schedule_bot.services.parity import week_number, week_parity
from schedule_bot.services.schedule import lessons_on, week_days

TELEGRAM_LIMIT = 4096

WEEKDAYS = [
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_GENITIVE = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]
TYPE_LABELS = {"lecture": "лекция", "seminar": "семинар", "lab": "лабораторная"}
TYPE_ICONS = {"lecture": "📖", "seminar": "💬", "lab": "🔬"}
PARITY_LABELS = {"every": "каждую неделю", "odd": "нечётные недели", "even": "чётные недели"}
PARITY_ADJECTIVES = {"odd": "нечётная", "even": "чётная"}


def format_date(day: date) -> str:
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}"


def format_lesson(lesson: Lesson, *, with_id: bool = False, with_parity: bool = False) -> str:
    """Two-line description of a lesson."""
    head = (
        f"{lesson.start:%H:%M}–{lesson.end:%H:%M} · <b>{escape(lesson.subject)}</b> "
        f"{TYPE_ICONS[lesson.type]} {TYPE_LABELS[lesson.type]}"
    )
    if with_parity and lesson.parity != "every":
        head += f" · {PARITY_LABELS[lesson.parity]}"
    if with_id:
        head = f"<code>#{lesson.id}</code> {head}"
    details = []
    if lesson.room:
        details.append(f"🚪 {escape(lesson.room)}")
    if lesson.teacher:
        details.append(f"👤 {escape(lesson.teacher)}")
    return head + ("\n    " + " · ".join(details) if details else "")


def format_day(title: str, day: date, lessons: Iterable[Lesson], semester_start: date) -> str:
    """Schedule of a single day, e.g. for /today and /tomorrow."""
    parity = PARITY_ADJECTIVES[week_parity(day, semester_start)]
    header = f"<b>{title}</b> — {WEEKDAYS[day.weekday()]}, {format_date(day)} ({parity} неделя)"
    todays = lessons_on(lessons, day, semester_start)
    if not todays:
        return f"{header}\n\n🎉 Занятий нет."
    body = "\n\n".join(format_lesson(lesson) for lesson in todays)
    return f"{header}\n\n{body}"


def format_week(today: date, lessons: Iterable[Lesson], semester_start: date) -> str:
    """Schedule of the current week (Monday-Sunday), empty days are skipped."""
    lessons = list(lessons)
    parity = PARITY_ADJECTIVES[week_parity(today, semester_start)]
    days = week_days(today)
    header = f"<b>Неделя {format_date(days[0])} – {format_date(days[-1])}</b> ({parity} неделя)"
    blocks = []
    for day in days:
        todays = lessons_on(lessons, day, semester_start)
        if not todays:
            continue
        marker = " 👈 сегодня" if day == today else ""
        lines = "\n".join(format_lesson(lesson) for lesson in todays)
        blocks.append(
            f"<b>{WEEKDAYS[day.weekday()].capitalize()}</b>, {format_date(day)}{marker}\n{lines}"
        )
    if not blocks:
        return f"{header}\n\n🎉 На этой неделе занятий нет."
    return header + "\n\n" + "\n\n".join(blocks)


def format_next(start: datetime, lesson: Lesson, now: datetime) -> str:
    delta = start - now
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if minutes or not parts:
        parts.append(f"{minutes} мин")
    when = (
        f"{WEEKDAYS[start.weekday()].capitalize()}, {format_date(start.date())}"
        if start.date() != now.date()
        else "Сегодня"
    )
    return f"<b>Следующая пара</b> — {when}, через {' '.join(parts)}\n\n{format_lesson(lesson)}"


def format_lesson_list(lessons: Iterable[Lesson]) -> str:
    """Full weekly template with ids (for /list)."""
    lessons = list(lessons)
    if not lessons:
        return "Расписание пусто. Добавьте пару через /add или загрузите CSV через /import."
    blocks = []
    for weekday in range(7):
        group = [lesson for lesson in lessons if lesson.weekday == weekday]
        if not group:
            continue
        lines = "\n".join(format_lesson(lesson, with_id=True, with_parity=True) for lesson in group)
        blocks.append(f"<b>{WEEKDAYS[weekday].capitalize()}</b>\n{lines}")
    return (
        "<b>Ваше расписание</b>\n\n" + "\n\n".join(blocks) + "\n\nУдалить пару: /delete &lt;id&gt;"
    )


def format_reminder(lesson: Lesson, minutes: int) -> str:
    return f"⏰ <b>Через {minutes} мин начнётся пара</b>\n\n{format_lesson(lesson)}"


def format_week_parity(today: date, semester_start: date) -> str:
    number = week_number(today, semester_start)
    current = week_parity(today, semester_start)
    opposite: Parity = "even" if current == "odd" else "odd"
    lines = [
        f"📆 Сейчас <b>{PARITY_ADJECTIVES[current]}</b> неделя"
        + (f" (№{number} семестра)." if number >= 1 else "."),
        f"Следующая неделя — {PARITY_ADJECTIVES[opposite]}.",
        f"Начало семестра: {semester_start:%d.%m.%Y}.",
    ]
    if number < 1:
        lines.append("Семестр ещё не начался.")
    return "\n".join(lines)


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split ``text`` on blank lines / newlines so every chunk fits Telegram's limit."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks
