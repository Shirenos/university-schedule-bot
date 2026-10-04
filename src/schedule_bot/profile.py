"""Bot profile (name, descriptions, command list, menu button) applied through the Bot API.

Run ``python -m schedule_bot.profile`` once after changing the texts below. The token is read
from ``BOT_TOKEN`` (env / ``.env``) and is never printed.

Telegram rate-limits ``setMyName`` strictly, so the name and descriptions are *not* touched on
every bot start; only the cheap command list and menu button are refreshed by :func:`main`.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands

from schedule_bot.config import ConfigError, load_settings

logger = logging.getLogger(__name__)

BOT_NAME = "Расписание вуза 🎓"  # <= 64 characters

SHORT_DESCRIPTION = (  # <= 120 characters
    "Расписание пар: сегодня, неделя, ближайшая пара, чётность недель и напоминания. "
    "ТулГУ — в один клик."
)

DESCRIPTION = (  # <= 512 characters, shown on the empty chat screen
    "🎓 Расписание занятий в Telegram\n\n"
    "📅 Пары на сегодня, завтра и всю неделю\n"
    "🏛 Загрузка расписания ТулГУ по номеру группы\n"
    "🔀 Выбор подгруппы: французский, немецкий, английский\n"
    "📆 Чётные и нечётные недели\n"
    "🔔 Напоминания перед парой\n\n"
    "Нажмите «Начать» и отправьте /tulgu 221461"
)

BOT_COMMANDS = [
    BotCommand(command="today", description="📅 Пары на сегодня"),
    BotCommand(command="tomorrow", description="🌅 Пары на завтра"),
    BotCommand(command="week", description="🗓 Расписание на неделю"),
    BotCommand(command="next", description="⏭ Ближайшая пара"),
    BotCommand(command="remind", description="🔔 Напоминания"),
    BotCommand(command="tulgu", description="🏛 Расписание ТулГУ по группе"),
    BotCommand(command="sync", description="🔄 Обновить расписание ТулГУ"),
    BotCommand(command="filters", description="🔀 Выбор подгруппы"),
    BotCommand(command="add", description="➕ Добавить пару"),
    BotCommand(command="list", description="📋 Всё расписание"),
    BotCommand(command="delete", description="🗑 Удалить пару по номеру"),
    BotCommand(command="import", description="📎 Импорт из CSV"),
    BotCommand(command="week_parity", description="📆 Чётная или нечётная неделя"),
    BotCommand(command="settings", description="⚙️ Настройки"),
    BotCommand(command="menu", description="📱 Показать меню"),
    BotCommand(command="help", description="❓ Справка"),
]


async def apply_commands(bot: Bot) -> None:
    """Command list (default scope) and the "commands" menu button; cheap, safe at every start."""
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def apply_profile(bot: Bot) -> list[str]:
    """Set name, descriptions, commands and menu button. Returns a list of failure messages."""
    steps = {
        "name": lambda: bot.set_my_name(name=BOT_NAME),
        "description": lambda: bot.set_my_description(description=DESCRIPTION),
        "short description": lambda: bot.set_my_short_description(
            short_description=SHORT_DESCRIPTION
        ),
        "commands": lambda: bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault()),
        "menu button": lambda: bot.set_chat_menu_button(menu_button=MenuButtonCommands()),
    }
    failures = []
    for title, call in steps.items():
        try:
            await call()
            print(f"✓ {title}")
        except TelegramAPIError as exc:
            failures.append(f"{title}: {exc.message}")
            print(f"✗ {title}: {exc.message}")
    return failures


async def _main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 2
    bot = Bot(settings.bot_token)
    try:
        failures = await apply_profile(bot)
    finally:
        await bot.session.close()
    return 1 if failures else 0


def run() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    run()
