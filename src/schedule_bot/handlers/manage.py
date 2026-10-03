"""/delete <id>."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from schedule_bot.db import Database
from schedule_bot.services.reminders import ReminderScheduler

router = Router(name="manage")


@router.message(Command("delete"))
async def cmd_delete(
    message: Message, command: CommandObject, db: Database, scheduler: ReminderScheduler
) -> None:
    assert message.from_user
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdigit():
        await message.answer("Укажите номер пары из /list, например: <code>/delete 3</code>")
        return
    user_id = message.from_user.id
    if await db.delete_lesson(user_id, int(arg)):
        scheduler.reschedule(user_id)
        await message.answer(f"🗑 Пара #{int(arg)} удалена.")
    else:
        await message.answer(f"Пара #{int(arg)} не найдена. Список номеров — /list.")
