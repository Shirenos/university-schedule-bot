"""Fake TulSU website for tests: the sample payload from tulsu.ru plus a controllable transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

GROUP = "221461"

DATES = {"MIN_DATE": "2026-08-31", "MAX_DATE": "2026-12-27", "SEARCH_FIELD": "GROUP_P"}


def entry(
    date: str,
    time: str,
    subject: str,
    kind: str,
    room: str,
    teacher: str,
    cls: str = "practice",
) -> dict[str, Any]:
    return {
        "DATE_Z": date,
        "TIME_Z": time,
        "DISCIP": subject,
        "KOW": kind,
        "AUD": room,
        "PREP": teacher,
        "GROUPS": [{"GROUP_P": GROUP, "PRIM": ""}],
        "CLASS": cls,
    }


# The first entry is the sample from the task description; the rest mirror the real structure:
# parallel French/German subgroups in one slot, an English subgroup in other slots, lectures, labs.
SAMPLE_PAYLOAD: list[dict[str, Any]] = [
    entry(
        "02.09.2026",
        "07:45 - 09:20",
        "Иностранный язык",
        "Практические занятия (фр)",
        "9-324",
        "Кондратьева Ирина Александровна",
    ),
    entry(
        "02.09.2026",
        "07:45 - 09:20",
        "Иностранный язык",
        "Практические занятия (нем)",
        "9-507",
        "Преподаватель Немецкий",
    ),
    entry(
        "02.09.2026",
        "11:35 - 13:10",
        "История России",
        "Лекции",
        "Гл.-431",
        "Преподаватель История",
        "lecture",
    ),
    entry(
        "04.09.2026",
        "13:40 - 15:15",
        "Иностранный язык",
        "Практические занятия (англ)",
        "9-210",
        "Преподаватель Английский",
    ),
    entry(
        "09.09.2026",
        "07:45 - 09:20",
        "Иностранный язык",
        "Практические занятия (фр)",
        "9-324",
        "Кондратьева Ирина Александровна",
    ),
    entry(
        "09.09.2026",
        "07:45 - 09:20",
        "Иностранный язык",
        "Практические занятия (нем)",
        "9-507",
        "Преподаватель Немецкий",
    ),
    entry(
        "10.09.2026",
        "09:40 - 11:15",
        "Информатика",
        "Лабораторные занятия",
        "К-12",
        "Преподаватель Информатика",
        "lab",
    ),
    # A class far in the future (after a gap) to exercise long look-ahead.
    entry(
        "11.01.2027",
        "09:40 - 11:15",
        "Информатика",
        "Лекции",
        "К-1",
        "Преподаватель Информатика",
        "lecture",
    ),
]


class TulguSite:
    """Records requests and answers like tulsu.ru; tweak attributes to simulate failures."""

    def __init__(self) -> None:
        self.payload: Any = SAMPLE_PAYLOAD
        self.dates: Any = DATES
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.raw_body: bytes | None = None
        self.fail: Callable[[httpx.Request], httpx.Response] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail is not None:
            return self.fail(request)
        if self.status != 200:
            return httpx.Response(self.status)
        if self.raw_body is not None:
            return httpx.Response(200, content=self.raw_body)
        group = request.url.params.get("search_value")
        known = group == GROUP
        if request.url.path.endswith("GetDates.php"):
            body = self.dates if known else {**DATES, "MIN_DATE": "", "MAX_DATE": ""}
            return httpx.Response(200, json=body)
        if request.url.path.endswith("GetSchedule.php"):
            return httpx.Response(200, json=self.payload if known else [])
        return httpx.Response(404)

    @property
    def paths(self) -> list[str]:
        return [request.url.path.rsplit("/", 1)[-1] for request in self.requests]

    def client(self, **kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler),
            headers={"User-Agent": "test"},
            **kwargs,
        )


def payload_json() -> str:
    return json.dumps(SAMPLE_PAYLOAD, ensure_ascii=False)
