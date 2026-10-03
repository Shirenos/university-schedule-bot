"""End-to-end test of the /add dialog through a real Dispatcher with a fake Telegram session."""

from __future__ import annotations

import itertools
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

from conftest import SEMESTER_START, TZ
from schedule_bot.config import Settings
from schedule_bot.handlers import build_router

# Routers can only be attached to one parent, so a single Dispatcher is shared by all tests;
# per-test state (db, scheduler) is injected through workflow_data and every test gets its own
# Telegram user id, which keeps the FSM storage isolated.
_DISPATCHER = Dispatcher()
_DISPATCHER.include_router(build_router())
_USER_IDS = itertools.count(1000)
FILES: dict[str, bytes] = {}


async def _fake_download(self, file, destination=None, **kwargs):
    """Stand-in for Bot.download: writes the canned file content into ``destination``."""
    destination.write(FILES[file.file_id])


class FakeSession(BaseSession):
    """Records outgoing API calls instead of talking to Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:  # pragma: no cover - nothing to close
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=len(self.calls),
                date=datetime.now(TZ),
                chat=Chat(id=method.chat_id, type="private"),
                from_user=User(id=1, is_bot=True, first_name="bot"),
                text=method.text,
            )
        return True

    @property
    def texts(self) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, SendMessage)]


@pytest.fixture
async def app(db, tmp_path, monkeypatch):
    monkeypatch.setattr(Bot, "download", _fake_download)
    user_id = next(_USER_IDS)
    user = {"id": user_id, "is_bot": False, "first_name": "Student"}
    chat = {"id": user_id, "type": "private"}
    session = FakeSession()
    bot = Bot("123456:TEST-TOKEN-NOT-REAL", session=session)
    settings = Settings(
        bot_token="x",
        database_path=tmp_path / "x.db",
        timezone=TZ,
        semester_start=SEMESTER_START,
    )
    scheduler = MagicMock()
    dp = _DISPATCHER
    dp.workflow_data.update(db=db, settings=settings, scheduler=scheduler)
    counter = iter(range(1, 1000))

    async def say(text: str) -> None:
        n = next(counter)
        update = Update.model_validate(
            {
                "update_id": n,
                "message": {
                    "message_id": n,
                    "date": 0,
                    "chat": chat,
                    "from": user,
                    "text": text,
                    "entities": (
                        [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
                        if text.startswith("/")
                        else []
                    ),
                },
            }
        )
        await dp.feed_update(bot, update)

    async def press(data: str) -> None:
        n = next(counter)
        update = Update.model_validate(
            {
                "update_id": n,
                "callback_query": {
                    "id": str(n),
                    "from": user,
                    "chat_instance": "1",
                    "data": data,
                    "message": {"message_id": 1, "date": 0, "chat": chat, "text": "q"},
                },
            }
        )
        await dp.feed_update(bot, update)

    async def send_file(content: bytes, caption: str | None = None) -> None:
        n = next(counter)
        FILES[f"file-{n}"] = content
        message: dict[str, Any] = {
            "message_id": n,
            "date": 0,
            "chat": chat,
            "from": user,
            "document": {
                "file_id": f"file-{n}",
                "file_unique_id": f"u{n}",
                "file_name": "schedule.csv",
                "file_size": len(content),
            },
        }
        if caption:
            message["caption"] = caption
        await dp.feed_update(bot, Update.model_validate({"update_id": n, "message": message}))

    return SimpleNamespace(
        session=session,
        say=say,
        send_file=send_file,
        press=press,
        scheduler=scheduler,
        user_id=user_id,
    )


async def test_full_add_dialog_saves_lesson(app, db):
    session, say, press, scheduler, uid = (
        app.session,
        app.say,
        app.press,
        app.scheduler,
        app.user_id,
    )
    await say("/add")
    await press("wd:2")
    await say("10:40-12:10")
    await say("Базы данных")
    await press("type:lab")
    await say("К-12")
    await say("-")
    await press("par:even")

    [lesson] = await db.list_lessons(uid)
    assert (lesson.weekday, lesson.start.strftime("%H:%M"), lesson.end.strftime("%H:%M")) == (
        2,
        "10:40",
        "12:10",
    )
    assert (lesson.subject, lesson.type, lesson.room, lesson.teacher, lesson.parity) == (
        "Базы данных",
        "lab",
        "К-12",
        "",
        "even",
    )
    assert "Пара добавлена" in session.texts[-1]
    scheduler.reschedule.assert_called_once_with(uid)


async def test_invalid_time_is_rejected_and_dialog_continues(app, db):
    session, say = app.session, app.say
    await say("/add")
    await say("пт")  # weekday typed as text
    await say("25:00-26:00")
    assert "неверное время" in session.texts[-1]
    await say("12:00-13:00")
    assert session.texts[-1] == "Название предмета:"


async def test_cancel_and_commands_work_inside_dialog(app, db):
    session, say, uid = app.session, app.say, app.user_id
    await say("/add")
    await say("/help")  # commands are not swallowed by the dialog
    assert "Команды" in session.texts[-1]
    await say("/cancel")
    assert session.texts[-1] == "Отменено."
    await say("/cancel")
    assert session.texts[-1] == "Нечего отменять."
    assert await db.count_lessons(uid) == 0


async def test_today_command_renders_schedule(app, db):
    session, say = app.session, app.say
    await say("/list")
    assert "Расписание пусто" in session.texts[-1]
    await say("/week_parity")
    assert "неделя" in session.texts[-1]
    await say("/next")
    assert "не найдено" in session.texts[-1]


CSV = (
    "weekday,start,end,subject,type,room,teacher,parity\n"
    "mon,09:00,10:30,Math,lecture,1,T,odd\n"
    "bad,1,2,x,y,,,\n"
)


async def test_import_dialog_with_partial_errors(app, db):
    await app.say("/import")
    assert "CSV" in app.session.texts[-1]
    await app.send_file(CSV.encode())
    assert "Импортировано пар: <b>1</b>" in app.session.texts[-1]
    assert "строка 3" in app.session.texts[-1]
    assert await db.count_lessons(app.user_id) == 1
    app.scheduler.reschedule.assert_called_once_with(app.user_id)


async def test_import_via_file_caption(app, db):
    await app.send_file(CSV.encode(), caption="/import")
    assert await db.count_lessons(app.user_id) == 1


async def test_import_rejects_bad_header(app, db):
    await app.say("/import")
    await app.send_file(b"a,b,c\n1,2,3\n")
    assert "Не хватает колонок" in app.session.texts[-1]
    assert await db.count_lessons(app.user_id) == 0


async def test_unrelated_documents_are_ignored(app, db):
    before = len(app.session.calls)
    await app.send_file(CSV.encode())
    assert len(app.session.calls) == before
