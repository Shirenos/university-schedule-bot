"""Read-only commands and their inline navigation: /today, /tomorrow, /week, /next, ..."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from schedule_bot.config import Settings
from schedule_bot.db import Database
from schedule_bot.handlers.keyboards import day_nav, next_nav, week_nav
from schedule_bot.services import formatting, schedule
from schedule_bot.services.parity import monday_of
from schedule_bot.services.timetable import load_timetable

router = Router(name="view")


# --- renderers (text + keyboard) ---------------------------------------------------------------


async def render_day(
    db: Database, settings: Settings, user_id: int, day: date
) -> tuple[str, InlineKeyboardMarkup]:
    now = settings.now()
    weekly, dated = await load_timetable(db, user_id)
    text = formatting.format_day(day, weekly, settings.semester_start, dated, now=now)
    text += f"\n<i>🔄 обновлено в {now:%H:%M}</i>"
    return formatting.fit_message(text), day_nav(day)


async def render_week(
    db: Database, settings: Settings, user_id: int, week_of: date
) -> tuple[str, InlineKeyboardMarkup]:
    now = settings.now()
    weekly, dated = await load_timetable(db, user_id)
    text = formatting.format_week(
        now.date(), weekly, settings.semester_start, dated, week_of=week_of
    )
    text += f"\n<i>🔄 обновлено в {now:%H:%M}</i>"
    return formatting.fit_message(text), week_nav(monday_of(week_of))


async def render_next(
    db: Database, settings: Settings, user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    now = settings.now()
    weekly, dated = await load_timetable(db, user_id)
    upcoming = schedule.next_lesson(weekly, now, settings.semester_start, dated)
    if upcoming is None:
        return formatting.format_no_next(), next_nav()
    start, lesson = upcoming
    text = formatting.format_next(start, lesson, now) + f"\n\n<i>🔄 обновлено в {now:%H:%M}</i>"
    return text, next_nav()


# --- actions shared by commands, menu buttons and inline buttons ---------------------------------


async def show_day(
    message: Message, db: Database, settings: Settings, user_id: int, offset: int = 0
) -> None:
    day = settings.now().date() + timedelta(days=offset)
    text, markup = await render_day(db, settings, user_id, day)
    await message.answer(text, reply_markup=markup)


async def show_week(message: Message, db: Database, settings: Settings, user_id: int) -> None:
    text, markup = await render_week(db, settings, user_id, settings.now().date())
    await message.answer(text, reply_markup=markup)


async def show_next(message: Message, db: Database, settings: Settings, user_id: int) -> None:
    text, markup = await render_next(db, settings, user_id)
    await message.answer(text, reply_markup=markup)


async def show_list(message: Message, db: Database, user_id: int) -> None:
    lessons = await db.list_lessons(user_id)
    text = formatting.format_lesson_list(lessons)
    tulgu = await db.get_tulgu(user_id)
    if tulgu is not None:
        count = await db.count_dated_lessons(user_id)
        text += (
            f"\n\n🏛 <b>ТулГУ</b>, группа {escape(tulgu.group)}: загружено занятий — {count}. "
            "Они показываются в /today, /week и /next."
        )
    for chunk in formatting.split_message(text):
        await message.answer(chunk)


async def show_parity(message: Message, settings: Settings) -> None:
    await message.answer(
        formatting.format_week_parity(settings.now().date(), settings.semester_start)
    )


# --- commands --------------------------------------------------------------------------------


@router.message(Command("today"))
async def cmd_today(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await show_day(message, db, settings, message.from_user.id, 0)


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await show_day(message, db, settings, message.from_user.id, 1)


@router.message(Command("week"))
async def cmd_week(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await show_week(message, db, settings, message.from_user.id)


@router.message(Command("next"))
async def cmd_next(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await show_next(message, db, settings, message.from_user.id)


@router.message(Command("week_parity"))
async def cmd_week_parity(message: Message, settings: Settings) -> None:
    await show_parity(message, settings)


@router.message(Command("list"))
async def cmd_list(message: Message, db: Database) -> None:
    assert message.from_user
    await show_list(message, db, message.from_user.id)


# --- inline navigation -----------------------------------------------------------------------


def _parse_day(argument: str, today: date) -> date | None:
    if argument == "today":
        return today
    try:
        day = date.fromisoformat(argument)
    except ValueError:
        return None
    return day if 2000 <= day.year <= 2100 else None


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    """Edit the message in place; Telegram rejects identical content, which is not an error."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
        await callback.answer("Уже актуально ✅")
        return
    await callback.answer()


@router.callback_query(F.data.startswith("day:"))
async def cb_day(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    day = _parse_day((callback.data or "")[4:], settings.now().date())
    if day is None:
        await callback.answer()
        return
    text, markup = await render_day(db, settings, callback.from_user.id, day)
    await _edit(callback, text, markup)


@router.callback_query(F.data.startswith("week:"))
async def cb_week(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    day = _parse_day((callback.data or "")[5:], settings.now().date())
    if day is None:
        await callback.answer()
        return
    text, markup = await render_week(db, settings, callback.from_user.id, day)
    await _edit(callback, text, markup)


@router.callback_query(F.data == "next:refresh")
async def cb_next(callback: CallbackQuery, db: Database, settings: Settings) -> None:
    text, markup = await render_next(db, settings, callback.from_user.id)
    await _edit(callback, text, markup)
