"""Inline keyboards for the /add dialog."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from schedule_bot.services.formatting import PARITY_LABELS, TYPE_LABELS, WEEKDAYS_SHORT


def weekday_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, name in enumerate(WEEKDAYS_SHORT):
        builder.button(text=name, callback_data=f"wd:{index}")
    builder.adjust(4, 3)
    return builder.as_markup()


def type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in TYPE_LABELS.items():
        builder.button(text=label.capitalize(), callback_data=f"type:{key}")
    builder.adjust(3)
    return builder.as_markup()


def parity_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in PARITY_LABELS.items():
        builder.button(text=label.capitalize(), callback_data=f"par:{key}")
    builder.adjust(1)
    return builder.as_markup()
