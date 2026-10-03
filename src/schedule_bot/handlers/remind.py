"""/remind on|off|<minutes>."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from schedule_bot.db import Database
from schedule_bot.models import MAX_REMIND_MINUTES
from schedule_bot.services.reminders import ReminderScheduler

router = Router(name="remind")

USAGE = (
    "Использование:\n"
    "<code>/remind on</code> — включить напоминания\n"
    "<code>/remind off</code> — выключить\n"
    "<code>/remind 30</code> — напоминать за 30 минут до начала пары"
)


@router.message(Command("remind"))
async def cmd_remind(
    message: Message, command: CommandObject, db: Database, scheduler: ReminderScheduler
) -> None:
    assert message.from_user
    user_id = message.from_user.id
    current = await db.get_reminder(user_id)
    arg = (command.args or "").strip().lower()

    if not arg:
        status = f"включены (за {current.minutes} мин)" if current.enabled else "выключены"
        await message.answer(f"🔔 Напоминания {status}.\n\n{USAGE}")
        return

    if arg == "off":
        await db.set_reminder(user_id, False, current.minutes)
        scheduler.cancel(user_id)
        await message.answer("🔕 Напоминания выключены.")
        return

    if arg == "on":
        minutes = current.minutes
    elif arg.isdigit() and 1 <= int(arg) <= MAX_REMIND_MINUTES:
        minutes = int(arg)
    else:
        await message.answer(f"Не понял. Минуты — число от 1 до {MAX_REMIND_MINUTES}.\n\n{USAGE}")
        return

    await db.set_reminder(user_id, True, minutes)
    scheduler.reschedule(user_id)
    await message.answer(f"🔔 Напоминания включены: за {minutes} мин до начала каждой пары.")
