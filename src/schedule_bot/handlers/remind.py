"""/remind on|off|<minutes> and the inline reminder panel."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from schedule_bot.db import Database
from schedule_bot.handlers.keyboards import remind_keyboard
from schedule_bot.models import MAX_REMIND_MINUTES
from schedule_bot.services.reminders import ReminderScheduler

router = Router(name="remind")

USAGE = (
    "Команды:\n"
    "<code>/remind on</code> — включить\n"
    "<code>/remind off</code> — выключить\n"
    "<code>/remind 30</code> — напоминать за 30 минут до пары"
)


async def render_panel(db: Database, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    current = await db.get_reminder(user_id)
    if current.enabled:
        status = f"🔔 <b>Включены</b> — за <b>{current.minutes} мин</b> до начала каждой пары."
    else:
        status = "🔕 <b>Выключены</b>. Включите — и я напомню о паре заранее."
    text = f"⏰ <b>Напоминания</b>\n━━━━━━━━━━━━━━━\n\n{status}\n\nВыберите время кнопками:"
    return text, remind_keyboard(current.enabled, current.minutes)


async def show_panel(message: Message, db: Database, user_id: int) -> None:
    text, markup = await render_panel(db, user_id)
    await message.answer(text, reply_markup=markup)


async def apply_setting(
    db: Database, scheduler: ReminderScheduler, user_id: int, arg: str
) -> str | None:
    """Apply ``on`` / ``off`` / ``<minutes>``. Returns a confirmation or ``None`` if invalid."""
    current = await db.get_reminder(user_id)
    arg = arg.strip().lower()
    if arg == "off":
        await db.set_reminder(user_id, False, current.minutes)
        scheduler.cancel(user_id)
        return "🔕 Напоминания выключены."
    if arg == "on":
        minutes = current.minutes
    elif arg.isdigit() and 1 <= int(arg) <= MAX_REMIND_MINUTES:
        minutes = int(arg)
    else:
        return None
    await db.set_reminder(user_id, True, minutes)
    scheduler.reschedule(user_id)
    return f"🔔 Напоминания включены: за {minutes} мин до начала каждой пары."


@router.message(Command("remind"))
async def cmd_remind(
    message: Message, command: CommandObject, db: Database, scheduler: ReminderScheduler
) -> None:
    assert message.from_user
    user_id = message.from_user.id
    arg = (command.args or "").strip()
    if not arg:
        await show_panel(message, db, user_id)
        return
    confirmation = await apply_setting(db, scheduler, user_id, arg)
    if confirmation is None:
        await message.answer(f"Не понял. Минуты — число от 1 до {MAX_REMIND_MINUTES}.\n\n{USAGE}")
        return
    await message.answer(confirmation)


@router.callback_query(F.data.startswith("rem:"))
async def cb_remind(callback: CallbackQuery, db: Database, scheduler: ReminderScheduler) -> None:
    user_id = callback.from_user.id
    confirmation = await apply_setting(db, scheduler, user_id, (callback.data or "")[4:])
    if confirmation is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    text, markup = await render_panel(db, user_id)
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
    await callback.answer("Сохранено ✅")
