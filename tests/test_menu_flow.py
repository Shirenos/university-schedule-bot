"""Menu, inline navigation, reminder panel and settings, end-to-end through the dispatcher."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import (
    AnswerCallbackQuery,
    SendMessage,
    SetChatMenuButton,
    SetMyCommands,
    SetMyDescription,
    SetMyName,
    SetMyShortDescription,
)
from aiogram.types import BotCommandScopeDefault, MenuButtonCommands, ReplyKeyboardMarkup

from conftest import ROOT_ROUTER, FakeSession, at, make_dated, make_lesson
from schedule_bot import profile
from schedule_bot.handlers import basic
from schedule_bot.handlers.keyboards import (
    BTN_NEXT,
    BTN_REMIND,
    BTN_SETTINGS,
    BTN_TODAY,
    BTN_TOMORROW,
    BTN_WEEK,
    main_menu,
)
from tulgu_data import GROUP

NOW = at("2026-10-05", "09:50")  # Monday


def buttons(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def last_markup(app):
    return app.session.calls[-1].reply_markup


async def seed(app, db):
    """Two days of dated lessons: Mon 5 and Tue 6 October 2026."""
    from datetime import date

    uid = app.user_id
    await db.replace_dated_lessons(
        uid,
        [
            make_dated(date(2026, 10, 5), "09:40", "11:15", subject="Алгебра", user_id=uid),
            make_dated(date(2026, 10, 5), "11:35", "13:10", subject="История", user_id=uid),
            make_dated(date(2026, 10, 6), "09:00", "10:30", subject="Физика", user_id=uid),
        ],
    )
    app.set_now(NOW)


# --- /start and reply keyboard -------------------------------------------------------------------


async def test_start_greets_with_menu_and_tulgu_hint(app):
    await app.say("/start")
    text = app.session.texts[-1]
    assert "Привет, <b>Student</b>" in text and "/tulgu 221461" in text
    markup = last_markup(app)
    assert isinstance(markup, ReplyKeyboardMarkup)
    assert markup.is_persistent and markup.resize_keyboard


async def test_start_escapes_the_user_name():
    message = SimpleNamespace(
        from_user=SimpleNamespace(first_name="<b>Eve</b> & co"), answer=AsyncMock()
    )
    await basic.cmd_start(message, AsyncMock())
    text = message.answer.call_args.args[0]
    assert "&lt;b&gt;Eve&lt;/b&gt; &amp; co" in text and "<b>Eve</b> &amp;" not in text


def test_main_menu_has_the_six_buttons_in_three_rows():
    rows = [[b.text for b in row] for row in main_menu().keyboard]
    assert rows == [
        [BTN_TODAY, BTN_TOMORROW],
        [BTN_WEEK, BTN_NEXT],
        [BTN_REMIND, BTN_SETTINGS],
    ]


async def test_menu_command_restores_the_keyboard(app):
    await app.say("/menu")
    assert isinstance(last_markup(app), ReplyKeyboardMarkup)


async def test_menu_buttons_trigger_the_views(app, db):
    await seed(app, db)
    await app.say(BTN_TODAY)
    assert "Понедельник, 5 октября" in app.session.texts[-1]
    assert "Алгебра" in app.session.texts[-1] and "идёт сейчас" in app.session.texts[-1]
    await app.say(BTN_TOMORROW)
    assert "Вторник, 6 октября" in app.session.texts[-1] and "Физика" in app.session.texts[-1]
    await app.say(BTN_WEEK)
    assert "5 – 11 октября" in app.session.texts[-1]
    await app.say(BTN_NEXT)
    assert "Следующая пара" in app.session.texts[-1] and "История" in app.session.texts[-1]
    await app.say(BTN_REMIND)
    assert "Напоминания" in app.session.texts[-1]
    await app.say(BTN_SETTINGS)
    assert "Настройки" in app.session.texts[-1]


async def test_menu_buttons_work_in_the_middle_of_a_dialog(app, db):
    await seed(app, db)
    await app.say("/add")
    await app.say(BTN_TODAY)
    assert "Понедельник, 5 октября" in app.session.texts[-1]
    await app.press("wd:2")  # the dialog is still alive
    assert "формате" in app.session.texts[-1]


# --- day / week navigation ---------------------------------------------------------------------


async def test_today_has_navigation_buttons(app, db):
    await seed(app, db)
    await app.say("/today")
    assert buttons(last_markup(app)) == [
        ("◀️", "day:2026-10-04"),
        ("📅 Сегодня", "day:today"),
        ("▶️", "day:2026-10-06"),
        ("🔄 Обновить", "day:2026-10-05"),
        ("🗓 Неделя", "week:2026-10-05"),
    ]


async def test_next_and_previous_day_edit_the_message_in_place(app, db):
    await seed(app, db)
    await app.say("/today")
    sent = len(app.session.texts)
    await app.press("day:2026-10-06")
    assert "Вторник, 6 октября" in app.session.edits[-1] and "Физика" in app.session.edits[-1]
    assert "завтра" in app.session.edits[-1]
    await app.press("day:2026-10-04")
    assert "Воскресенье, 4 октября" in app.session.edits[-1]
    assert "Занятий нет" in app.session.edits[-1] and "вчера" in app.session.edits[-1]
    await app.press("day:today")
    assert "Понедельник, 5 октября" in app.session.edits[-1]
    assert len(app.session.texts) == sent  # nothing new was sent, only edits


async def test_refresh_when_nothing_changed_is_not_an_error(app, db):
    await seed(app, db)
    await app.press("day:2026-10-05")
    await app.press("day:2026-10-05")  # same minute, identical content
    answer = app.session.calls[-1]
    assert isinstance(answer, AnswerCallbackQuery) and "актуально" in answer.text


async def test_refresh_picks_up_changes(app, db):
    await seed(app, db)
    await app.press("day:2026-10-05")
    assert "идёт сейчас" in app.session.edits[-1] and "Алгебра" in app.session.edits[-1]
    app.set_now(at("2026-10-05", "11:20"))
    await app.press("day:2026-10-05")
    assert "идёт сейчас" not in app.session.edits[-1]
    assert "⏭ <b>следующая</b>" in app.session.edits[-1]


async def test_week_navigation(app, db):
    await seed(app, db)
    await app.say("/week")
    assert "эта неделя" in app.session.texts[-1]
    assert ("▶️", "week:2026-10-12") in buttons(last_markup(app))
    await app.press("week:2026-10-12")
    assert "12 – 18 октября" in app.session.edits[-1]
    assert "следующая неделя" in app.session.edits[-1]
    assert "Занятий нет" in app.session.edits[-1] or "занятий нет" in app.session.edits[-1]
    await app.press("week:today")
    assert "5 – 11 октября" in app.session.edits[-1]
    await app.press("week:2026-10-06")  # any day of the week selects that week
    assert "5 – 11 октября" in app.session.edits[-1] or "актуально" in str(app.session.calls[-1])


async def test_garbage_callbacks_are_ignored(app, db):
    await seed(app, db)
    before = len(app.session.edits)
    for data in ["day:garbage", "day:9999-12-31", "week:2026-13-45", "week:", "day:"]:
        await app.press(data)
    assert len(app.session.edits) == before


async def test_next_refresh_button(app, db):
    await seed(app, db)
    await app.say("/next")
    assert ("🔄 Обновить", "next:refresh") in buttons(last_markup(app))
    app.set_now(at("2026-10-05", "12:00"))
    await app.press("next:refresh")
    assert "Физика" in app.session.edits[-1]  # next is now tomorrow's 09:00 lesson


async def test_next_without_lessons_is_friendly(app):
    await app.say("/next")
    assert "Ближайших занятий нет" in app.session.texts[-1]


# --- reminder panel ----------------------------------------------------------------------------


async def test_reminder_panel_buttons(app, db):
    await app.say("/remind")
    assert "Выключены" in app.session.texts[-1]
    assert ("🔔 Включить", "rem:on") in buttons(last_markup(app))

    await app.press("rem:on")
    assert (await db.get_reminder(app.user_id)).enabled
    assert "Включены" in app.session.edits[-1] and "15 мин" in app.session.edits[-1]
    app.scheduler.reschedule.assert_called_with(app.user_id)

    await app.press("rem:30")
    state = await db.get_reminder(app.user_id)
    assert (state.enabled, state.minutes) == (True, 30)
    kb = app.session.calls[-2].reply_markup  # the edit that carried the new panel
    assert ("✅ 30 мин", "rem:30") in buttons(kb) and ("🔕 Выключить", "rem:off") in buttons(kb)

    await app.press("rem:off")
    assert not (await db.get_reminder(app.user_id)).enabled
    app.scheduler.cancel.assert_called_with(app.user_id)

    edits = len(app.session.edits)
    await app.press("rem:abc")
    await app.press("rem:0")
    assert len(app.session.edits) == edits


# --- settings panel ----------------------------------------------------------------------------


async def test_settings_panel_reflects_state(app, db):
    await app.say("/settings")
    text = app.session.texts[-1]
    assert "не подключено" in text and "выключены" in text and "Europe/Moscow" in text
    assert {data for _, data in buttons(last_markup(app))} == {
        f"menu:{a}" for a in ["sync", "tulgu", "filters", "remind", "add", "list", "parity", "help"]
    }

    await app.say(f"/tulgu {GROUP}")
    await db.set_reminder(app.user_id, True, 20)
    await app.say(BTN_SETTINGS)
    text = app.session.texts[-1]
    assert f"группа <b>{GROUP}</b>" in text and "за <b>20 мин</b>" in text


async def test_settings_actions(app, db):
    await app.press("menu:sync")
    assert "Группа не выбрана" in app.session.texts[-1]
    await app.press("menu:tulgu")
    assert "/tulgu 221461" in app.session.texts[-1]
    await app.press("menu:filters")
    assert "Сначала подключите" in app.session.texts[-1]

    await app.say(f"/tulgu {GROUP}")
    requests = len(app.site.requests)
    await app.press("menu:sync")  # served from cache, still reports
    assert any("из кэша" in text for text in app.session.texts[-5:])
    assert len(app.site.requests) == requests
    await app.press("menu:tulgu")
    assert f"<b>{GROUP}</b>" in app.session.texts[-1]
    await app.press("menu:filters")
    assert "Параллельные подгруппы" in app.session.texts[-2]

    await app.press("menu:parity")
    assert "Чётность недели" in app.session.texts[-1]
    await app.press("menu:list")
    assert "ТулГУ" in app.session.texts[-1]
    await app.press("menu:help")
    assert "Справка" in app.session.texts[-1]
    await app.press("menu:remind")
    assert "Напоминания" in app.session.texts[-1]


async def test_settings_add_starts_the_dialog(app, db):
    await app.press("menu:add")
    assert "Новая пара" in app.session.texts[-1] and "Шаг 1 из 7" in app.session.texts[-1]
    await app.press("wd:1")
    await app.say("09:00-10:30")
    await app.say("Химия")
    await app.press("type:lab")
    await app.say("-")
    await app.say("-")
    await app.press("par:every")
    assert [lesson.subject for lesson in await db.list_lessons(app.user_id)] == ["Химия"]


# --- bot profile -------------------------------------------------------------------------------


@pytest.fixture
def profile_bot():
    session = FakeSession()
    return Bot("123456:TEST-TOKEN-NOT-REAL", session=session), session


async def test_apply_profile_calls_every_profile_method(profile_bot):
    bot, session = profile_bot
    assert await profile.apply_profile(bot) == []
    by_type = {type(call): call for call in session.calls}
    assert by_type[SetMyName].name == profile.BOT_NAME
    assert by_type[SetMyDescription].description == profile.DESCRIPTION
    assert by_type[SetMyShortDescription].short_description == profile.SHORT_DESCRIPTION
    commands = by_type[SetMyCommands]
    assert commands.commands == profile.BOT_COMMANDS
    assert isinstance(commands.scope, BotCommandScopeDefault)
    assert isinstance(by_type[SetChatMenuButton].menu_button, MenuButtonCommands)
    assert by_type[SetChatMenuButton].menu_button.type == "commands"


async def test_apply_profile_reports_failures_and_continues(profile_bot, capsys):
    bot, session = profile_bot
    session.fail_methods = {SetMyName}
    failures = await profile.apply_profile(bot)
    assert len(failures) == 1 and failures[0].startswith("name:")
    assert SetMyCommands in {type(call) for call in session.calls}  # later steps still ran
    assert "TEST-TOKEN" not in capsys.readouterr().out


async def test_startup_refreshes_only_commands_and_menu_button(profile_bot):
    bot, session = profile_bot
    await profile.apply_commands(bot)
    assert {type(call) for call in session.calls} == {SetMyCommands, SetChatMenuButton}
    assert SendMessage not in {type(call) for call in session.calls}


def test_profile_texts_respect_telegram_limits():
    assert len(profile.BOT_NAME) <= 64
    assert len(profile.SHORT_DESCRIPTION) <= 120
    assert len(profile.DESCRIPTION) <= 512
    assert 1 <= len(profile.BOT_COMMANDS) <= 100
    for command in profile.BOT_COMMANDS:
        assert command.command.islower() or "_" in command.command
        assert 1 <= len(command.command) <= 32 and 1 <= len(command.description) <= 256
    names = [c.command for c in profile.BOT_COMMANDS]
    assert len(names) == len(set(names))
    assert {"today", "tomorrow", "week", "next", "remind", "tulgu", "sync", "help"} <= set(names)


def test_every_listed_command_has_a_handler():
    registered: set[str] = set()
    for router in ROOT_ROUTER.sub_routers:
        for handler in router.message.handlers:
            for flt in handler.filters:
                commands = getattr(flt.callback, "commands", ())
                registered.update(str(c) for c in commands)
    missing = {c.command for c in profile.BOT_COMMANDS} - registered
    assert not missing, f"commands without a handler: {missing}"


def test_make_lesson_helper_still_importable():  # keeps conftest helpers exercised
    assert make_lesson().subject == "Math"


def test_avatar_is_a_square_png_ready_for_botfather():
    import struct
    from pathlib import Path

    data = (Path(__file__).parent.parent / "docs" / "avatar.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert width == height >= 640
