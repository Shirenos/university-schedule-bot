"""Entry point: wires config, database, scheduler and the aiogram dispatcher."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from schedule_bot.config import ConfigError, load_settings
from schedule_bot.db import Database
from schedule_bot.handlers import build_router
from schedule_bot.profile import apply_commands
from schedule_bot.services.reminders import ReminderScheduler
from schedule_bot.services.sync import SyncService
from schedule_bot.services.tulgu import TulguClient

logger = logging.getLogger(__name__)


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
        try:
            await apply_commands(bot)
        except TelegramAPIError:
            logger.warning("Could not update the command list / menu button", exc_info=True)
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
