"""/start, /help, /menu and /cancel."""

from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from schedule_bot.handlers import texts
from schedule_bot.handlers.keyboards import main_menu

router = Router(name="basic")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = escape(message.from_user.first_name) if message.from_user else "студент"
    await message.answer(texts.START.format(name=name), reply_markup=main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer(texts.MENU_HINT, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Отменено.")
