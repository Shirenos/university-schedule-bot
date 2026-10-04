from __future__ import annotations

import itertools
from datetime import date, datetime, time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

from schedule_bot.config import Settings
from schedule_bot.db import Database
from schedule_bot.handlers import build_router
from schedule_bot.main import create_bot
from schedule_bot.models import DatedLesson, Lesson
from schedule_bot.services.sync import SyncService
from schedule_bot.services.tulgu import TulguClient
from tulgu_data import TulguSite

TZ = ZoneInfo("Europe/Moscow")
# Monday, 2026-09-07 is the first day of week 1 (odd); week 2 (even) starts 2026-09-14.
SEMESTER_START = date(2026, 9, 7)


def make_lesson(
    weekday: int = 0,
    start: str = "09:00",
    end: str = "10:30",
    *,
    subject: str = "Math",
    type: str = "lecture",
    room: str = "101",
    teacher: str = "Ivanov",
    parity: str = "every",
    user_id: int = 1,
    id: int | None = None,
) -> Lesson:
    return Lesson(
        user_id=user_id,
        weekday=weekday,
        start=time.fromisoformat(start),
        end=time.fromisoformat(end),
        subject=subject,
        type=type,  # type: ignore[arg-type]
        room=room,
        teacher=teacher,
        parity=parity,  # type: ignore[arg-type]
        id=id,
    )


def make_dated(
    day: date,
    start: str = "09:00",
    end: str = "10:30",
    *,
    subject: str = "Math",
    kind: str = "Лекции",
    type: str = "lecture",
    room: str = "101",
    teacher: str = "Ivanov",
    user_id: int = 1,
) -> DatedLesson:
    return DatedLesson(
        user_id=user_id,
        date=day,
        start=time.fromisoformat(start),
        end=time.fromisoformat(end),
        subject=subject,
        kind=kind,
        type=type,  # type: ignore[arg-type]
        room=room,
        teacher=teacher,
        group="221461",
    )


def at(day: str, clock: str = "00:00") -> datetime:
    return datetime.combine(date.fromisoformat(day), time.fromisoformat(clock), tzinfo=TZ)


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def tulgu_site() -> TulguSite:
    return TulguSite()


# Routers can only be attached to one parent, so a single Dispatcher is shared by all tests;
# per-test state (db, scheduler) is injected through workflow_data and every test gets its own
# Telegram user id, which keeps the FSM storage isolated.
_DISPATCHER = Dispatcher()
ROOT_ROUTER = build_router()
_DISPATCHER.include_router(ROOT_ROUTER)
_USER_IDS = itertools.count(1000)
FILES: dict[str, bytes] = {}


async def _fake_download(self, file, destination=None, **kwargs):
    """Stand-in for Bot.download: writes the canned file content into ``destination``."""
    destination.write(FILES[file.file_id])


async def _no_sleep(_: float) -> None:
    return None


class FakeSession(BaseSession):
    """Records outgoing API calls instead of talking to Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.fail_methods: set[type] = set()  # API methods that should fail with BadRequest
        self._last_edit: dict[tuple[Any, Any], tuple[str, Any]] = {}

    async def close(self) -> None:  # pragma: no cover - nothing to close
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None):
        self.calls.append(method)
        if type(method) in self.fail_methods:
            raise TelegramBadRequest(method=method, message="Bad Request: simulated failure")
        if isinstance(method, EditMessageText):
            # Like Telegram: re-sending identical text and markup is an error.
            key = (method.chat_id, method.message_id)
            content = (method.text, method.reply_markup)
            if self._last_edit.get(key) == content:
                raise TelegramBadRequest(
                    method=method, message="Bad Request: message is not modified"
                )
            self._last_edit[key] = content
            return True
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

    @property
    def edits(self) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, EditMessageText)]

    @property
    def keyboards(self) -> list[Any]:
        return [m.reply_markup for m in self.calls if isinstance(m, SendMessage) and m.reply_markup]


@pytest.fixture
async def app(db, tmp_path, monkeypatch, tulgu_site):
    monkeypatch.setattr(Bot, "download", _fake_download)
    user_id = next(_USER_IDS)
    user = {"id": user_id, "is_bot": False, "first_name": "Student"}
    chat = {"id": user_id, "type": "private"}
    session = FakeSession()
    bot = create_bot("123456:TEST-TOKEN-NOT-REAL", session=session)
    settings = Settings(
        bot_token="x",
        database_path=tmp_path / "x.db",
        timezone=TZ,
        semester_start=SEMESTER_START,
    )
    scheduler = MagicMock()
    tulgu_client = TulguClient(client=tulgu_site.client(), sleep=_no_sleep)
    sync_service = SyncService(db, tulgu_client)
    dp = _DISPATCHER
    dp.workflow_data.update(
        db=db, settings=settings, scheduler=scheduler, sync_service=sync_service
    )
    clock = {"now": datetime.now(TZ)}
    monkeypatch.setattr(Settings, "now", lambda self: clock["now"])

    def set_now(value: datetime) -> None:
        clock["now"] = value

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
        set_now=set_now,
        site=tulgu_site,
        sync_service=sync_service,
    )
