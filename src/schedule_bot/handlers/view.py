"""Read-only commands: /today, /tomorrow, /week, /next, /week_parity, /list."""

from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from schedule_bot.config import Settings
from schedule_bot.db import Database
from schedule_bot.services import formatting, schedule

router = Router(name="view")


async def _answer_long(message: Message, text: str) -> None:
    for chunk in formatting.split_message(text):
        await message.answer(chunk)


@router.message(Command("today"))
async def cmd_today(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    today = settings.now().date()
    lessons = await db.list_lessons(message.from_user.id)
    await message.answer(formatting.format_day("Сегодня", today, lessons, settings.semester_start))


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    tomorrow = settings.now().date() + timedelta(days=1)
    lessons = await db.list_lessons(message.from_user.id)
    await message.answer(
        formatting.format_day("Завтра", tomorrow, lessons, settings.semester_start)
    )


@router.message(Command("week"))
async def cmd_week(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    today = settings.now().date()
    lessons = await db.list_lessons(message.from_user.id)
    await _answer_long(message, formatting.format_week(today, lessons, settings.semester_start))


@router.message(Command("next"))
async def cmd_next(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    now = settings.now()
    lessons = await db.list_lessons(message.from_user.id)
    upcoming = schedule.next_lesson(lessons, now, settings.semester_start)
    if upcoming is None:
        await message.answer("Ближайших занятий не найдено. Добавьте пары через /add.")
        return
    start, lesson = upcoming
    await message.answer(formatting.format_next(start, lesson, now))


@router.message(Command("week_parity"))
async def cmd_week_parity(message: Message, settings: Settings) -> None:
    await message.answer(
        formatting.format_week_parity(settings.now().date(), settings.semester_start)
    )


@router.message(Command("list"))
async def cmd_list(message: Message, db: Database) -> None:
    assert message.from_user
    lessons = await db.list_lessons(message.from_user.id)
    await _answer_long(message, formatting.format_lesson_list(lessons))
