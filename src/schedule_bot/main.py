"""Entry point: wires config, database, scheduler and the aiogram dispatcher."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from schedule_bot.config import ConfigError, load_settings
from schedule_bot.db import Database
from schedule_bot.handlers import build_router
from schedule_bot.services.reminders import ReminderScheduler
from schedule_bot.services.sync import SyncService
from schedule_bot.services.tulgu import TulguClient

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="today", description="Пары на сегодня"),
    BotCommand(command="tomorrow", description="Пары на завтра"),
    BotCommand(command="week", description="Расписание на неделю"),
    BotCommand(command="next", description="Ближайшая пара"),
    BotCommand(command="tulgu", description="Расписание ТулГУ по номеру группы"),
    BotCommand(command="sync", description="Обновить расписание ТулГУ"),
    BotCommand(command="filters", description="Выбор подгруппы"),
    BotCommand(command="add", description="Добавить пару"),
    BotCommand(command="list", description="Всё расписание"),
    BotCommand(command="delete", description="Удалить пару по номеру"),
    BotCommand(command="import", description="Импорт из CSV"),
    BotCommand(command="remind", description="Напоминания: on / off / минуты"),
    BotCommand(command="week_parity", description="Чётная или нечётная неделя"),
    BotCommand(command="help", description="Справка"),
]


async def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    db = Database(settings.database_path)
    await db.connect()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = ReminderScheduler(db, bot.send_message, settings.timezone, settings.semester_start)
    await scheduler.start()

    tulgu_client = TulguClient()
    sync_service = SyncService(db, tulgu_client)

    dp = Dispatcher(db=db, settings=settings, scheduler=scheduler, sync_service=sync_service)
    dp.include_router(build_router())

    try:
        await bot.set_my_commands(BOT_COMMANDS)
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        await scheduler.stop()
        await tulgu_client.aclose()
        await bot.session.close()
        await db.close()


def run() -> None:
    try:
        asyncio.run(main())
    except ConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    except KeyboardInterrupt:
        logger.info("Bot stopped")


if __name__ == "__main__":
    run()
