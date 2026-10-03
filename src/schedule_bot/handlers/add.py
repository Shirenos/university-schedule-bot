"""Guided /add dialog built on aiogram FSM."""

from __future__ import annotations

from datetime import time
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from schedule_bot.db import Database
from schedule_bot.handlers.keyboards import parity_keyboard, type_keyboard, weekday_keyboard
from schedule_bot.models import MAX_LESSONS_PER_USER, Lesson
from schedule_bot.services import formatting
from schedule_bot.services.parsing import (
    ParseError,
    parse_parity,
    parse_time_range,
    parse_type,
    parse_weekday,
)
from schedule_bot.services.reminders import ReminderScheduler

router = Router(name="add")

MAX_TEXT_LENGTH = 200
SKIP = "-"

# Text steps ignore messages starting with "/" so that unknown commands are never swallowed.
_TEXT = F.text & ~F.text.startswith("/")


class AddLesson(StatesGroup):
    weekday = State()
    time = State()
    subject = State()
    type = State()
    room = State()
    teacher = State()
    parity = State()


async def _ask_time(message: Message, state: FSMContext, weekday: int) -> None:
    await state.update_data(weekday=weekday)
    await state.set_state(AddLesson.time)
    await message.answer(
        f"День: <b>{formatting.WEEKDAYS[weekday]}</b>.\n\n"
        "Введите время пары в формате <code>09:00-10:30</code>:"
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext, db: Database) -> None:
    assert message.from_user
    if await db.count_lessons(message.from_user.id) >= MAX_LESSONS_PER_USER:
        await message.answer(
            f"Достигнут лимит: {MAX_LESSONS_PER_USER} пар. Удалите лишние (/list)."
        )
        return
    await state.clear()
    await state.set_state(AddLesson.weekday)
    await message.answer(
        "➕ <b>Новая пара</b> (отмена — /cancel)\n\nВыберите день недели:",
        reply_markup=weekday_keyboard(),
    )


@router.callback_query(StateFilter(AddLesson.weekday), F.data.startswith("wd:"))
async def step_weekday_button(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_time(callback.message, state, int((callback.data or "wd:0").split(":")[1]))


@router.message(StateFilter(AddLesson.weekday), _TEXT)
async def step_weekday_text(message: Message, state: FSMContext) -> None:
    try:
        weekday = parse_weekday(message.text or "")
    except ParseError:
        await message.answer("Не понял день недели. Нажмите кнопку или напишите, например, «пн».")
        return
    await _ask_time(message, state, weekday)


@router.message(StateFilter(AddLesson.time), _TEXT)
async def step_time(message: Message, state: FSMContext) -> None:
    try:
        start, end = parse_time_range(message.text or "")
    except ParseError as exc:
        await message.answer(f"⚠️ {escape(str(exc))}\nПример: <code>09:00-10:30</code>")
        return
    await state.update_data(start=start.strftime("%H:%M"), end=end.strftime("%H:%M"))
    await state.set_state(AddLesson.subject)
    await message.answer("Название предмета:")


@router.message(StateFilter(AddLesson.subject), _TEXT)
async def step_subject(message: Message, state: FSMContext) -> None:
    subject = (message.text or "").strip()
    if not subject or len(subject) > MAX_TEXT_LENGTH:
        await message.answer(f"Название должно быть от 1 до {MAX_TEXT_LENGTH} символов.")
        return
    await state.update_data(subject=subject)
    await state.set_state(AddLesson.type)
    await message.answer("Тип занятия:", reply_markup=type_keyboard())


@router.callback_query(StateFilter(AddLesson.type), F.data.startswith("type:"))
async def step_type(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        lesson_type = parse_type((callback.data or "").split(":", 1)[1])
    except (ParseError, IndexError):
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(type=lesson_type)
    await state.set_state(AddLesson.room)
    await callback.message.answer(f"Аудитория (или «{SKIP}», чтобы пропустить):")


@router.message(StateFilter(AddLesson.room), _TEXT)
async def step_room(message: Message, state: FSMContext) -> None:
    room = (message.text or "").strip()
    if len(room) > MAX_TEXT_LENGTH:
        await message.answer("Слишком длинно, сократите.")
        return
    await state.update_data(room="" if room == SKIP else room)
    await state.set_state(AddLesson.teacher)
    await message.answer(f"Преподаватель (или «{SKIP}», чтобы пропустить):")


@router.message(StateFilter(AddLesson.teacher), _TEXT)
async def step_teacher(message: Message, state: FSMContext) -> None:
    teacher = (message.text or "").strip()
    if len(teacher) > MAX_TEXT_LENGTH:
        await message.answer("Слишком длинно, сократите.")
        return
    await state.update_data(teacher="" if teacher == SKIP else teacher)
    await state.set_state(AddLesson.parity)
    await message.answer("На каких неделях проходит пара?", reply_markup=parity_keyboard())


@router.callback_query(StateFilter(AddLesson.parity), F.data.startswith("par:"))
async def step_parity(
    callback: CallbackQuery, state: FSMContext, db: Database, scheduler: ReminderScheduler
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        parity = parse_parity((callback.data or "").split(":", 1)[1])
    except (ParseError, IndexError):
        return
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)

    user_id = callback.from_user.id
    lesson = Lesson(
        user_id=user_id,
        weekday=data["weekday"],
        start=time.fromisoformat(data["start"]),
        end=time.fromisoformat(data["end"]),
        subject=data["subject"],
        type=data["type"],
        room=data["room"],
        teacher=data["teacher"],
        parity=parity,
    )
    lesson_id = await db.add_lesson(lesson)
    scheduler.reschedule(user_id)
    await callback.message.answer(
        f"✅ Пара добавлена (<code>#{lesson_id}</code>)\n\n"
        f"<b>{formatting.WEEKDAYS[lesson.weekday].capitalize()}</b>\n"
        f"{formatting.format_lesson(lesson, with_parity=True)}"
    )
