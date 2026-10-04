"""Client for the public JSON endpoints behind https://tulsu.ru/schedule/ (TulSU).

The site publishes the timetable of a student group as a flat JSON list of *dated* lessons.
No authentication is needed. The client is deliberately gentle with the server: it sends a
descriptive User-Agent, uses short timeouts, retries only transient failures a couple of times
and keeps a small in-memory cache so repeated syncs of the same group do not hit the site.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

import httpx

from schedule_bot import __version__
from schedule_bot.models import DatedLesson, LessonType

logger = logging.getLogger(__name__)

BASE_URL = "https://tulsu.ru/schedule/queries"
USER_AGENT = (
    f"university-schedule-bot/{__version__} "
    "(+https://github.com/Shirenos/university-schedule-bot; personal timetable reader)"
)
DEFAULT_TIMEOUT = 10.0
DEFAULT_CACHE_TTL = 300.0  # seconds
MAX_ATTEMPTS = 3
RETRY_DELAY = 1.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

GROUP_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё._()/-]{1,20}$")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})")

CLASS_TYPES: dict[str, LessonType] = {"lecture": "lecture", "practice": "seminar", "lab": "lab"}


class TulguError(RuntimeError):
    """Base class for sync problems; ``str(exc)`` is a user-facing Russian message."""


class GroupNotFoundError(TulguError):
    """The site knows no timetable for the requested group."""


def is_valid_group(value: str) -> bool:
    return bool(GROUP_RE.match(value))


@dataclass(frozen=True, slots=True)
class TulguSchedule:
    """Result of one download, independent of any Telegram user."""

    group: str
    min_date: date | None
    max_date: date | None
    lessons: tuple[DatedLesson, ...] = field(default_factory=tuple)
    fetched_at: datetime | None = None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _lesson_type(class_name: str, kind: str) -> LessonType:
    if class_name in CLASS_TYPES:
        return CLASS_TYPES[class_name]
    lowered = kind.lower()
    if lowered.startswith("лекц"):
        return "lecture"
    if lowered.startswith("лаб"):
        return "lab"
    return "seminar"


def parse_lessons(payload: Any, group: str, user_id: int = 0) -> list[DatedLesson]:
    """Convert the ``GetSchedule.php`` payload.

    Malformed entries are skipped and exact duplicates dropped.
    """
    if not isinstance(payload, list):
        raise TulguError("Сайт ТулГУ вернул неожиданный ответ. Попробуйте позже.")
    lessons: list[DatedLesson] = []
    seen: set[tuple[object, ...]] = set()
    for item in payload:
        try:
            day = datetime.strptime(_clean(item["DATE_Z"]), "%d.%m.%Y").date()
            match = _TIME_RE.search(_clean(item["TIME_Z"]))
            if not match:
                raise ValueError("bad time")
            h1, m1, h2, m2 = (int(g) for g in match.groups())
            start, end = time(h1, m1), time(h2, m2)
            subject = _clean(item["DISCIP"])
            if not subject or end <= start:
                raise ValueError("empty subject or reversed time")
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed timetable entry %r: %s", item, exc)
            continue
        kind = _clean(item.get("KOW"))
        lesson = DatedLesson(
            user_id=user_id,
            date=day,
            start=start,
            end=end,
            subject=subject,
            kind=kind,
            type=_lesson_type(_clean(item.get("CLASS")), kind),
            room=_clean(item.get("AUD")),
            teacher=_clean(item.get("PREP")),
            group=group,
        )
        key = (day, start, end, subject, kind, lesson.room, lesson.teacher)
        if key not in seen:
            seen.add(key)
            lessons.append(lesson)
    lessons.sort(key=lambda lesson: (lesson.date, lesson.start, lesson.kind))
    return lessons


def _parse_iso(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


class TulguClient:
    """Async client with a User-Agent, timeouts, light retries and a per-group TTL cache."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        clock: Callable[[], float] = _time.monotonic,
        sleep: Callable[[float], Any] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=4),
        )
        self._base_url = base_url.rstrip("/")
        self._cache_ttl = cache_ttl
        self._clock = clock
        self._sleep = sleep
        self._now = now
        self._cache: dict[str, tuple[float, TulguSchedule]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def cached(self, group: str) -> TulguSchedule | None:
        """The cached schedule if it is still fresh."""
        entry = self._cache.get(group)
        if entry and self._clock() - entry[0] < self._cache_ttl:
            return entry[1]
        return None

    async def fetch(self, group: str, *, force: bool = False) -> TulguSchedule:
        """Download (or return the cached) timetable of ``group``.

        ``force`` skips the cache but results are still stored, so concurrent callers share
        one download. Raises :class:`TulguError` subclasses with Russian messages.
        """
        group = group.strip()
        if not is_valid_group(group):
            raise TulguError("Некорректный номер группы. Пример: <code>/tulgu 221461</code>")
        lock = self._locks.setdefault(group, asyncio.Lock())
        async with lock:
            if not force and (hit := self.cached(group)):
                return hit
            schedule = await self._download(group)
            self._cache[group] = (self._clock(), schedule)
            return schedule

    async def _download(self, group: str) -> TulguSchedule:
        dates = await self._get_json("GetDates.php", {"search_value": group})
        min_date = _parse_iso(dates.get("MIN_DATE")) if isinstance(dates, dict) else None
        max_date = _parse_iso(dates.get("MAX_DATE")) if isinstance(dates, dict) else None
        if min_date is None:
            raise GroupNotFoundError(f"Группа {group} не найдена на сайте ТулГУ.")
        payload = await self._get_json(
            "GetSchedule.php", {"search_field": "GROUP_P", "search_value": group}
        )
        lessons = parse_lessons(payload, group)
        if not lessons:
            raise GroupNotFoundError(f"Для группы {group} на сайте ТулГУ пока нет занятий.")
        return TulguSchedule(group, min_date, max_date, tuple(lessons), self._now())

    async def _get_json(self, endpoint: str, params: dict[str, str]) -> Any:
        url = f"{self._base_url}/{endpoint}"
        last_error = "неизвестная ошибка"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.get(url, params=params)
            except httpx.TimeoutException:
                last_error = "превышено время ожидания"
            except httpx.HTTPError as exc:
                last_error = f"ошибка соединения ({type(exc).__name__})"
            else:
                if response.status_code >= 500:
                    last_error = f"сервер ответил {response.status_code}"
                elif response.status_code != 200:
                    raise TulguError(f"Сайт ТулГУ ответил кодом {response.status_code}.")
                elif len(response.content) > MAX_RESPONSE_BYTES:
                    raise TulguError("Ответ сайта ТулГУ слишком большой.")
                else:
                    try:
                        return response.json()
                    except ValueError:
                        raise TulguError(
                            "Сайт ТулГУ вернул не JSON. Возможно, он на обслуживании."
                        ) from None
            logger.warning(
                "%s attempt %d/%d failed: %s", endpoint, attempt, MAX_ATTEMPTS, last_error
            )
            if attempt < MAX_ATTEMPTS:
                await self._sleep(RETRY_DELAY * attempt)
        raise TulguError(f"Не удалось связаться с сайтом ТулГУ: {last_error}. Попробуйте позже.")
