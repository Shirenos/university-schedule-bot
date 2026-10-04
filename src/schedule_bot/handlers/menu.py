"""Main menu: reply-keyboard buttons and the inline settings panel."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from schedule_bot.config import Settings
from schedule_bot.db import Database
from schedule_bot.handlers import add, remind, texts, tulgu, view
from schedule_bot.handlers.keyboards import (
    BTN_NEXT,
    BTN_REMIND,
    BTN_SETTINGS,
    BTN_TODAY,
    BTN_TOMORROW,
    BTN_WEEK,
    settings_menu,
)
from schedule_bot.services import formatting
from schedule_bot.services.reminders import ReminderScheduler
from schedule_bot.services.sync import SyncService

router = Router(name="menu")


async def render_settings(db: Database, settings: Settings, user_id: int) -> str:
    tulgu_settings = await db.get_tulgu(user_id)
    reminder = await db.get_reminder(user_id)
    group = (
        f"группа <b>{escape(tulgu_settings.group)}</b>"
        if tulgu_settings
        else "не подключено (<code>/tulgu 221461</code>)"
    )
    remind_text = f"за <b>{reminder.minutes} мин</b>" if reminder.enabled else "выключены"
    today = settings.now().date()
    return (
        f"⚙️ <b>Настройки</b>\n{texts.SEP}\n\n"
        f"🏛 ТулГУ: {group}\n"
        f"🔔 Напоминания: {remind_text}\n"
        f"📆 Сейчас {formatting.parity_phrase(today, settings.semester_start)}\n"
        f"🌍 Часовой пояс: {escape(str(settings.timezone))}"
    )


# --- reply keyboard buttons ---------------------------------------------------------------------


@router.message(F.text == BTN_TODAY)
async def btn_today(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await view.show_day(message, db, settings, message.from_user.id, 0)


@router.message(F.text == BTN_TOMORROW)
async def btn_tomorrow(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await view.show_day(message, db, settings, message.from_user.id, 1)


@router.message(F.text == BTN_WEEK)
async def btn_week(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await view.show_week(message, db, settings, message.from_user.id)


@router.message(F.text == BTN_NEXT)
async def btn_next(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await view.show_next(message, db, settings, message.from_user.id)


@router.message(F.text == BTN_REMIND)
async def btn_remind(message: Message, db: Database) -> None:
    assert message.from_user
    await remind.show_panel(message, db, message.from_user.id)


@router.message(F.text == BTN_SETTINGS)
@router.message(Command("settings"))
async def btn_settings(message: Message, db: Database, settings: Settings) -> None:
    assert message.from_user
    await message.answer(
        await render_settings(db, settings, message.from_user.id), reply_markup=settings_menu()
    )


# --- inline settings panel ------------------------------------------------------------------


@router.callback_query(F.data.startswith("menu:"))
async def cb_menu(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
    sync_service: SyncService,
    scheduler: ReminderScheduler,
) -> None:
    await callback.answer()
    message = callback.message
    if not isinstance(message, Message):
        return
    user_id = callback.from_user.id
    action = (callback.data or "")[5:]
    if action == "sync":
        await tulgu.run_sync(message, user_id, db, settings, sync_service, scheduler)
    elif action == "tulgu":
        await tulgu.show_status(message, user_id, db, settings)
    elif action == "filters":
        await tulgu.show_filters(message, user_id, db, sync_service)
    elif action == "remind":
        await remind.show_panel(message, db, user_id)
    elif action == "add":
        await add.start_add(message, state, db, user_id)
    elif action == "list":
        await view.show_list(message, db, user_id)
    elif action == "parity":
        await view.show_parity(message, settings)
    elif action == "help":
        await message.answer(texts.HELP)
