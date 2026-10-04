"""Reply and inline keyboards."""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from schedule_bot.services.filters import VariantGroup
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


def filter_keyboard(group: VariantGroup) -> InlineKeyboardMarkup:
    """One button per parallel variant plus "show all"; callback data is ``flt:<token>:<i|a>``."""
    builder = InlineKeyboardBuilder()
    for index, option in enumerate(group.options):
        builder.button(text=option, callback_data=f"flt:{group.token}:{index}")
    builder.button(text="Показывать все", callback_data=f"flt:{group.token}:a")
    builder.adjust(3)
    return builder.as_markup()


# --- main menu (reply keyboard) ------------------------------------------------------------

BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "🌅 Завтра"
BTN_WEEK = "🗓 Неделя"
BTN_NEXT = "⏭ Следующая пара"
BTN_REMIND = "🔔 Напоминания"
BTN_SETTINGS = "⚙️ Настройки"

MENU_PLACEHOLDER = "Выберите действие…"


def main_menu() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard with the everyday actions."""
    rows = [
        [BTN_TODAY, BTN_TOMORROW],
        [BTN_WEEK, BTN_NEXT],
        [BTN_REMIND, BTN_SETTINGS],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=MENU_PLACEHOLDER,
    )


# --- navigation (inline) ---------------------------------------------------------------------


def day_nav(day: date) -> InlineKeyboardMarkup:
    """◀️ day ▶️ navigation for /today and /tomorrow; callback data is ``day:<iso|today>``."""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️", callback_data=f"day:{(day - timedelta(days=1)).isoformat()}")
    builder.button(text="📅 Сегодня", callback_data="day:today")
    builder.button(text="▶️", callback_data=f"day:{(day + timedelta(days=1)).isoformat()}")
    builder.button(text="🔄 Обновить", callback_data=f"day:{day.isoformat()}")
    builder.button(text="🗓 Неделя", callback_data=f"week:{day.isoformat()}")
    builder.adjust(3, 2)
    return builder.as_markup()


def week_nav(monday: date) -> InlineKeyboardMarkup:
    """◀️ week ▶️ navigation; callback data is ``week:<iso|today>``."""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️", callback_data=f"week:{(monday - timedelta(days=7)).isoformat()}")
    builder.button(text="🗓 Эта неделя", callback_data="week:today")
    builder.button(text="▶️", callback_data=f"week:{(monday + timedelta(days=7)).isoformat()}")
    builder.button(text="🔄 Обновить", callback_data=f"week:{monday.isoformat()}")
    builder.button(text="📅 День", callback_data=f"day:{monday.isoformat()}")
    builder.adjust(3, 2)
    return builder.as_markup()


def next_nav() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="next:refresh")
    builder.button(text="📅 Сегодня", callback_data="day:today")
    builder.button(text="🗓 Неделя", callback_data="week:today")
    builder.adjust(3)
    return builder.as_markup()


def settings_menu() -> InlineKeyboardMarkup:
    """Inline settings / quick actions menu; callback data is ``menu:<action>``."""
    builder = InlineKeyboardBuilder()
    for text, action in [
        ("🔄 Синхронизировать", "sync"),
        ("🏛 Группа ТулГУ", "tulgu"),
        ("🔀 Подгруппы", "filters"),
        ("🔔 Напоминания", "remind"),
        ("➕ Добавить пару", "add"),
        ("📋 Всё расписание", "list"),
        ("📆 Чётность недели", "parity"),
        ("❓ Помощь", "help"),
    ]:
        builder.button(text=text, callback_data=f"menu:{action}")
    builder.adjust(2)
    return builder.as_markup()


REMIND_PRESETS = (5, 10, 15, 30, 60)


def remind_keyboard(enabled: bool, minutes: int) -> InlineKeyboardMarkup:
    """On/off toggle and lead-time presets; callback data is ``rem:<on|off|minutes>``."""
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.button(text="🔕 Выключить", callback_data="rem:off")
    else:
        builder.button(text="🔔 Включить", callback_data="rem:on")
    for preset in REMIND_PRESETS:
        mark = "✅ " if enabled and preset == minutes else ""
        builder.button(text=f"{mark}{preset} мин", callback_data=f"rem:{preset}")
    builder.adjust(1, 3, 2)
    return builder.as_markup()
