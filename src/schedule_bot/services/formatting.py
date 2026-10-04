"""Render schedule data as Telegram HTML messages (Russian UI).

All user-supplied text (subjects, rooms, teachers, ...) is passed through :func:`html.escape`
before being embedded in markup.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from html import escape, unescape
from typing import Literal

from schedule_bot.models import DatedLesson, Lesson, Parity
from schedule_bot.services.links import room_url
from schedule_bot.services.parity import monday_of, week_number, week_parity
from schedule_bot.services.schedule import lessons_on, week_days

TELEGRAM_LIMIT = 4096

SEPARATOR = "━━━━━━━━━━━━━━━"

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
TYPE_ICONS = {"lecture": "📚", "seminar": "✏️", "lab": "🔬"}
LANGUAGE_ICON = "🌐"
_LANGUAGE_RE = re.compile(
    r"иностран|английск|немецк|французск|испанск|китайск|english|german|french|foreign",
    re.IGNORECASE,
)
PARITY_LABELS = {"every": "каждую неделю", "odd": "нечётные недели", "even": "чётные недели"}
PARITY_ADJECTIVES = {"odd": "нечётная", "even": "чётная"}
RELATIVE_DAYS = {-1: "вчера", 0: "сегодня", 1: "завтра", 2: "послезавтра"}

Status = Literal["", "done", "now", "next"]


# --- small helpers -----------------------------------------------------------------------------


def format_date(day: date) -> str:
    """``5 октября``."""
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}"


def format_day_title(day: date) -> str:
    """``Понедельник, 5 октября``."""
    return f"{WEEKDAYS[day.weekday()].capitalize()}, {format_date(day)}"


def format_time_range(start: time, end: time) -> str:
    """``09:00 – 10:30``."""
    return f"{start:%H:%M} – {end:%H:%M}"


def format_range(first: date, last: date) -> str:
    """``5 – 11 октября`` or ``28 сентября – 4 октября``."""
    if first.month == last.month and first.year == last.year:
        return f"{first.day} – {format_date(last)}"
    return f"{format_date(first)} – {format_date(last)}"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural form: 1 пара, 2 пары, 5 пар."""
    if 11 <= n % 100 <= 14:
        form = many
    elif n % 10 == 1:
        form = one
    elif 2 <= n % 10 <= 4:
        form = few
    else:
        form = many
    return f"{n} {form}"


def short_name(name: str) -> str:
    """``Иванов Иван Иванович`` -> ``Иванов И. И.``; anything else is returned unchanged."""
    parts = name.split()
    if (
        len(parts) == 3
        and not any("." in part for part in parts)
        and all(p.isalpha() for p in parts)
    ):
        return f"{parts[0]} {parts[1][0]}. {parts[2][0]}."
    return name


def lesson_icon(lesson: Lesson) -> str:
    """Emoji by lesson type; language classes get their own icon."""
    if _LANGUAGE_RE.search(lesson.subject):
        return LANGUAGE_ICON
    return TYPE_ICONS[lesson.type]


def lesson_label(lesson: Lesson) -> str:
    return lesson.label or TYPE_LABELS[lesson.type]


def parity_phrase(day: date, semester_start: date) -> str:
    """``нечётная неделя №5`` (the number is omitted before the semester starts)."""
    text = f"{PARITY_ADJECTIVES[week_parity(day, semester_start)]} неделя"
    number = week_number(day, semester_start)
    return f"{text} №{number}" if number >= 1 else text


# --- lesson cards ------------------------------------------------------------------------------

_STATUS_BADGES = {
    "now": " · 🟢 <b>идёт сейчас</b>",
    "next": " · ⏭ <b>следующая</b>",
    "done": " · ✔️",
}


def link(text: str, url: str | None) -> str:
    """``<a href>`` with escaped text and URL; plain escaped text when there is no URL."""
    if not url:
        return escape(text)
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def room_html(lesson: Lesson) -> str:
    """The room, linked to its building on the map when the building is known."""
    return link(lesson.room, room_url(lesson.room))


def _details(lesson: Lesson) -> str:
    parts = []
    if lesson.room:
        parts.append(f"📍 {room_html(lesson)}")
    if lesson.teacher:
        parts.append(f"👤 {link(short_name(lesson.teacher), lesson.teacher_url)}")
    return " · ".join(parts)


def format_lesson(
    lesson: Lesson,
    *,
    with_id: bool = False,
    with_parity: bool = False,
    status: Status = "",
) -> str:
    """A lesson card.

    ::

        🕘 09:00 – 10:30 · 🟢 идёт сейчас
        📚 История России · лекция
        📍 Гл.-431 · 👤 Чугунова Н. В.
    """
    time_text = format_time_range(lesson.start, lesson.end)
    time_line = f"🕘 <b>{time_text}</b>" if status != "done" else f"🕘 <s>{time_text}</s>"
    if with_id:
        time_line = f"<code>#{lesson.id}</code> {time_line}"
    title = f"{lesson_icon(lesson)} <b>{escape(lesson.subject)}</b> · {lesson_label(lesson)}"
    if with_parity and lesson.parity != "every":
        title += f" · 🔁 {PARITY_LABELS[lesson.parity]}"
    lines = [time_line + _STATUS_BADGES.get(status, ""), title]
    if details := _details(lesson):
        lines.append(details)
    return "\n".join(lines)


def format_lesson_line(lesson: Lesson) -> str:
    """One compact line for the week view: start time, icon, subject and room."""
    line = f"<code>{lesson.start:%H:%M}</code> {lesson_icon(lesson)} {escape(lesson.subject)}"
    if lesson.room:
        line += f" · 📍{room_html(lesson)}"
    return line


def _statuses(lessons: list[Lesson], day: date, now: datetime | None) -> list[Status]:
    """Done / now / next markers; only meaningful for the current day."""
    if now is None or now.date() != day:
        return [""] * len(lessons)
    current = now.time().replace(tzinfo=None)
    result: list[Status] = []
    next_marked = False
    for lesson in lessons:
        if lesson.end <= current:
            result.append("done")
        elif lesson.start <= current:
            result.append("now")
        elif not next_marked:
            result.append("next")
            next_marked = True
        else:
            result.append("")
    return result


# --- day / week / next -------------------------------------------------------------------------


def format_day(
    day: date,
    lessons: Iterable[Lesson],
    semester_start: date,
    dated: Iterable[DatedLesson] = (),
    now: datetime | None = None,
) -> str:
    """Schedule of a single day.

    When ``now`` is given the day is labelled (сегодня / завтра / ...) and, for the current
    day, lessons are marked as finished, in progress ("идёт сейчас") or next.
    """
    todays = lessons_on(lessons, day, semester_start, dated)
    subtitle = parity_phrase(day, semester_start)
    if now is not None and (relative := RELATIVE_DAYS.get((day - now.date()).days)):
        subtitle = f"{relative} · {subtitle}"
    header = f"📅 <b>{format_day_title(day)}</b>\n<i>{subtitle}</i>\n{SEPARATOR}"

    if not todays:
        return (
            f"{header}\n\n🌿 <b>Занятий нет</b>\n"
            "Свободный день — отдохните или займитесь своими делами ☕"
        )

    statuses = _statuses(todays, day, now)
    cards = "\n\n".join(
        format_lesson(lesson, status=status)
        for lesson, status in zip(todays, statuses, strict=True)
    )
    span = f"с {todays[0].start:%H:%M} до {max(lesson.end for lesson in todays):%H:%M}"
    footer = f"📊 {plural(len(todays), 'пара', 'пары', 'пар')} · {span}"
    if statuses and all(status == "done" for status in statuses):
        footer += "\n🏁 На сегодня всё — отдыхайте!"
    return f"{header}\n\n{cards}\n\n{SEPARATOR}\n{footer}"


def format_week(
    today: date,
    lessons: Iterable[Lesson],
    semester_start: date,
    dated: Iterable[DatedLesson] = (),
    week_of: date | None = None,
) -> str:
    """Compact schedule of a week (Monday-Sunday) containing ``week_of`` (default: today)."""
    lessons = list(lessons)
    dated = list(dated)
    days = week_days(week_of or today)
    delta_weeks = (days[0] - monday_of(today)).days // 7
    relative = {-1: "прошлая неделя", 0: "эта неделя", 1: "следующая неделя"}.get(delta_weeks)
    subtitle = parity_phrase(days[0], semester_start)
    if relative:
        number = week_number(days[0], semester_start)
        adjective = PARITY_ADJECTIVES[week_parity(days[0], semester_start)]
        subtitle = f"{relative} · {adjective}" + (f" №{number}" if number >= 1 else "")
    header = f"🗓 <b>{format_range(days[0], days[-1])}</b>\n<i>{subtitle}</i>\n{SEPARATOR}"

    blocks: list[str] = []
    free: list[str] = []
    total = 0
    for day in days:
        todays = lessons_on(lessons, day, semester_start, dated)
        if not todays:
            free.append(WEEKDAYS_SHORT[day.weekday()])
            continue
        total += len(todays)
        mark = "🔹" if day == today else "▫️"
        tail = " — <i>сегодня</i>" if day == today else ""
        title = f"{mark} <b>{WEEKDAYS_SHORT[day.weekday()]}, {format_date(day)}</b>{tail}"
        blocks.append(title + "\n" + "\n".join(format_lesson_line(lesson) for lesson in todays))

    if not blocks:
        return f"{header}\n\n🌿 <b>На этой неделе занятий нет</b>\nМожно выдохнуть ☕"
    text = f"{header}\n\n" + "\n\n".join(blocks)
    if free:
        text += f"\n\n🌿 Свободно: {', '.join(free)}"
    return f"{text}\n{SEPARATOR}\n📊 Всего: {plural(total, 'пара', 'пары', 'пар')}"


def format_duration(delta: timedelta) -> str:
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if minutes or not parts:
        parts.append(f"{minutes} мин")
    return " ".join(parts)


def format_next(start: datetime, lesson: Lesson, now: datetime) -> str:
    when = RELATIVE_DAYS.get((start.date() - now.date()).days)
    if when is None or (start.date() - now.date()).days < 0:
        when = f"{WEEKDAYS[start.weekday()]}, {format_date(start.date())}"
    return (
        f"⏭ <b>Следующая пара</b>\n"
        f"<i>через {format_duration(start - now)} · {when}</i>\n"
        f"{SEPARATOR}\n\n{format_lesson(lesson)}"
    )


def format_no_next() -> str:
    return (
        "🌿 <b>Ближайших занятий нет</b>\n\n"
        "Добавьте пары через /add или загрузите расписание группы: <code>/tulgu 221461</code>"
    )


# --- list, reminders, parity ---------------------------------------------------------------


def format_lesson_list(lessons: Iterable[Lesson]) -> str:
    """Full weekly template with ids (for /list)."""
    lessons = list(lessons)
    if not lessons:
        return (
            "📋 <b>Расписание пусто</b>\n\n"
            "Добавьте пару через /add, загрузите CSV через /import "
            "или подключите расписание ТулГУ: <code>/tulgu 221461</code>"
        )
    blocks = []
    for weekday in range(7):
        group = [lesson for lesson in lessons if lesson.weekday == weekday]
        if not group:
            continue
        cards = "\n\n".join(
            format_lesson(lesson, with_id=True, with_parity=True) for lesson in group
        )
        blocks.append(f"▫️ <b>{WEEKDAYS[weekday].capitalize()}</b>\n{cards}")
    return (
        f"📋 <b>Ваше расписание</b>\n{SEPARATOR}\n\n"
        + "\n\n".join(blocks)
        + f"\n\n{SEPARATOR}\nУдалить пару: <code>/delete номер</code>"
    )


def format_reminder(lesson: Lesson, minutes: int) -> str:
    return f"⏰ <b>Через {minutes} мин — пара!</b>\n{SEPARATOR}\n\n{format_lesson(lesson)}"


def format_week_parity(today: date, semester_start: date) -> str:
    number = week_number(today, semester_start)
    current = week_parity(today, semester_start)
    opposite: Parity = "even" if current == "odd" else "odd"
    lines = [
        "📆 <b>Чётность недели</b>",
        SEPARATOR,
        "",
        f"Сейчас <b>{PARITY_ADJECTIVES[current]}</b> неделя"
        + (f" (№{number} семестра)." if number >= 1 else "."),
        f"Следующая — {PARITY_ADJECTIVES[opposite]}.",
        "",
        f"🎓 Начало семестра: {semester_start:%d.%m.%Y}",
    ]
    if number < 1:
        lines.append("Семестр ещё не начался.")
    return "\n".join(lines)


_TAG_RE = re.compile(r"<[^>]+>")


def visible_length(html_text: str) -> int:
    """Length Telegram counts against its 4096 limit: the text without tags and URLs."""
    return len(unescape(_TAG_RE.sub("", html_text)))


def fit_message(text: str, limit: int = TELEGRAM_LIMIT) -> str:
    """Trim ``text`` to ``limit`` visible characters on a line boundary (for edited messages)."""
    if visible_length(text) <= limit:
        return text
    lines = text.split("\n")
    while len(lines) > 1 and visible_length("\n".join(lines)) > limit - 2:
        lines.pop()
    return "\n".join(lines) + "\n…"


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split ``text`` on newlines so every chunk fits Telegram's limit (links count as text)."""
    if visible_length(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if visible_length(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while visible_length(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks
