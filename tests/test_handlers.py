from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram.filters import CommandObject

from conftest import make_lesson
from schedule_bot.handlers import manage, remind


def fake_message(user_id: int = 1):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id), answer=AsyncMock())


def command(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="x", args=args)


async def test_remind_on_off_and_minutes(db):
    scheduler = MagicMock()
    message = fake_message()

    await remind.cmd_remind(message, command("on"), db, scheduler)
    state = await db.get_reminder(1)
    assert (state.enabled, state.minutes) == (True, 15)
    scheduler.reschedule.assert_called_with(1)

    await remind.cmd_remind(message, command("30"), db, scheduler)
    state = await db.get_reminder(1)
    assert (state.enabled, state.minutes) == (True, 30)

    await remind.cmd_remind(message, command("off"), db, scheduler)
    state = await db.get_reminder(1)
    assert (state.enabled, state.minutes) == (False, 30)
    scheduler.cancel.assert_called_with(1)


async def test_remind_rejects_garbage_and_shows_status(db):
    scheduler = MagicMock()
    message = fake_message()
    await remind.cmd_remind(message, command("soon"), db, scheduler)
    await remind.cmd_remind(message, command("0"), db, scheduler)
    await remind.cmd_remind(message, command("99999"), db, scheduler)
    assert (await db.get_reminder(1)).enabled is False
    scheduler.reschedule.assert_not_called()

    await remind.cmd_remind(message, command(None), db, scheduler)
    assert "Выключены" in message.answer.call_args.args[0]
    assert message.answer.call_args.kwargs["reply_markup"] is not None


async def test_delete_command(db):
    scheduler = MagicMock()
    lesson_id = await db.add_lesson(make_lesson(user_id=1))
    other = fake_message(user_id=2)
    await manage.cmd_delete(other, command(str(lesson_id)), db, scheduler)
    assert "не найдена" in other.answer.call_args.args[0]
    assert await db.count_lessons(1) == 1

    mine = fake_message(user_id=1)
    await manage.cmd_delete(mine, command(f"#{lesson_id}"), db, scheduler)
    assert "удалена" in mine.answer.call_args.args[0]
    assert await db.count_lessons(1) == 0
    scheduler.reschedule.assert_called_once_with(1)

    await manage.cmd_delete(mine, command("abc"), db, scheduler)
    assert "Укажите номер" in mine.answer.call_args.args[0]
