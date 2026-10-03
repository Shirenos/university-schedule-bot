"""/import: load a schedule from an uploaded CSV file."""

from __future__ import annotations

import io

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from schedule_bot.db import Database
from schedule_bot.handlers import texts
from schedule_bot.models import MAX_LESSONS_PER_USER
from schedule_bot.services.csv_import import MAX_FILE_SIZE, CsvImportError, parse_csv_bytes
from schedule_bot.services.reminders import ReminderScheduler

router = Router(name="importer")

MAX_ERRORS_SHOWN = 5


class ImportCsv(StatesGroup):
    waiting_file = State()


# Command() also matches captions, so a file sent with the "/import" caption is excluded here
# and handled by import_with_caption below.
@router.message(Command("import"), ~F.document)
async def cmd_import(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ImportCsv.waiting_file)
    await message.answer(texts.IMPORT_PROMPT)


async def _import_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    scheduler: ReminderScheduler,
) -> None:
    assert message.from_user and message.document
    document = message.document
    if document.file_size and document.file_size > MAX_FILE_SIZE:
        await message.answer("Файл слишком большой (максимум 256 КБ).")
        return

    buffer = io.BytesIO()
    await bot.download(document, destination=buffer)
    user_id = message.from_user.id
    try:
        result = parse_csv_bytes(buffer.getvalue(), user_id)
    except CsvImportError as exc:
        await message.answer(f"⚠️ {exc}\n\nПроверьте файл и пришлите его снова или нажмите /cancel.")
        return

    existing = await db.count_lessons(user_id)
    if existing + len(result.lessons) > MAX_LESSONS_PER_USER:
        await message.answer(
            f"Слишком много пар: лимит {MAX_LESSONS_PER_USER} на пользователя "
            f"(сейчас {existing}, в файле {len(result.lessons)})."
        )
        return

    await state.clear()
    imported = await db.add_lessons(result.lessons)
    if imported:
        scheduler.reschedule(user_id)

    lines = [f"✅ Импортировано пар: <b>{imported}</b>."]
    if result.errors:
        lines.append(f"Пропущено строк с ошибками: <b>{len(result.errors)}</b>")
        shown = result.errors[:MAX_ERRORS_SHOWN]
        lines.extend(f"• строка {line}: {text}" for line, text in shown)
        if len(result.errors) > len(shown):
            lines.append(f"… и ещё {len(result.errors) - len(shown)}")
    if imported:
        lines.append("\nПосмотреть результат: /list")
    await message.answer("\n".join(lines))


@router.message(StateFilter(ImportCsv.waiting_file), F.document)
async def import_in_dialog(
    message: Message, state: FSMContext, bot: Bot, db: Database, scheduler: ReminderScheduler
) -> None:
    await _import_document(message, state, bot, db, scheduler)


@router.message(F.document, F.caption.startswith("/import"))
async def import_with_caption(
    message: Message, state: FSMContext, bot: Bot, db: Database, scheduler: ReminderScheduler
) -> None:
    await _import_document(message, state, bot, db, scheduler)


@router.message(StateFilter(ImportCsv.waiting_file))
async def import_wrong_input(message: Message) -> None:
    await message.answer("Жду CSV-файл документом. Отмена — /cancel.")
