import httpx
import pytest

from schedule_bot.services.tulgu import (
    USER_AGENT,
    GroupNotFoundError,
    TulguClient,
    TulguError,
    is_valid_group,
    parse_lessons,
)
from tulgu_data import GROUP, SAMPLE_PAYLOAD, TulguSite, entry


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def no_sleep(_: float) -> None:
    return None


def make_client(site: TulguSite, clock: Clock | None = None, **kwargs) -> TulguClient:
    return TulguClient(client=site.client(), sleep=no_sleep, clock=clock or Clock(), **kwargs)


# --- parsing ---------------------------------------------------------------------------------


def test_parse_lessons_maps_the_sample_entry():
    first = next(
        lesson
        for lesson in parse_lessons(SAMPLE_PAYLOAD, GROUP, user_id=5)
        if lesson.kind.endswith("(фр)")
    )
    assert first.date.isoformat() == "2026-09-02"
    assert (first.start.strftime("%H:%M"), first.end.strftime("%H:%M")) == ("07:45", "09:20")
    assert first.subject == "Иностранный язык"
    assert first.kind == "Практические занятия (фр)"
    assert first.type == "seminar"  # CLASS "practice"
    assert (first.room, first.teacher) == ("9-324", "Кондратьева Ирина Александровна")
    assert (first.group, first.user_id) == (GROUP, 5)


def test_parse_lessons_class_types():
    types = {lesson.subject: lesson.type for lesson in parse_lessons(SAMPLE_PAYLOAD, GROUP)}
    assert types["История России"] == "lecture"
    assert types["Информатика"] in {"lab", "lecture"}
    by_kind = {lesson.kind: lesson.type for lesson in parse_lessons(SAMPLE_PAYLOAD, GROUP)}
    assert by_kind["Лабораторные занятия"] == "lab"


def test_parse_lessons_falls_back_to_kind_when_class_is_unknown():
    [lesson] = parse_lessons(
        [entry("02.09.2026", "08:00 - 09:00", "X", "Лекции", "1", "T", "")], "g"
    )
    assert lesson.type == "lecture"


def test_parse_lessons_skips_malformed_and_duplicates():
    good = entry("02.09.2026", "08:00 - 09:30", "Math", "Лекции", "1", "T", "lecture")
    payload = [
        good,
        dict(good),  # exact duplicate
        {**good, "DATE_Z": "2026-09-02"},  # wrong date format
        {**good, "TIME_Z": "soon"},
        {**good, "TIME_Z": "10:00 - 09:00"},
        {**good, "DISCIP": "  "},
        {"nonsense": True},
        "string",
    ]
    assert len(parse_lessons(payload, "g")) == 1


def test_parse_lessons_normalises_whitespace_and_en_dash():
    [lesson] = parse_lessons(
        [entry("02.09.2026", "8:00 – 9:30", " Math \n 1 ", "Лекции", " 1 ", "T")], "g"
    )
    assert lesson.subject == "Math 1"
    assert lesson.start.hour == 8 and lesson.end.minute == 30


def test_parse_lessons_rejects_non_list():
    with pytest.raises(TulguError):
        parse_lessons({"error": 1}, "g")


@pytest.mark.parametrize("value", ["221461", "ИС-21", "22.1461", "a" * 20])
def test_valid_groups(value):
    assert is_valid_group(value)


@pytest.mark.parametrize("value", ["", " ", "a b", "a" * 21, "22;DROP", "<b>", "1&2"])
def test_invalid_groups(value):
    assert not is_valid_group(value)


# --- HTTP client -----------------------------------------------------------------------------


async def test_fetch_requests_both_endpoints_with_user_agent_and_params():
    site = TulguSite()
    client = TulguClient(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(site.handler), headers={"User-Agent": USER_AGENT}
        ),
        sleep=no_sleep,
    )
    schedule = await client.fetch(GROUP)

    assert site.paths == ["GetDates.php", "GetSchedule.php"]
    dates_request, schedule_request = site.requests
    assert dict(dates_request.url.params) == {"search_value": GROUP}
    assert dict(schedule_request.url.params) == {"search_field": "GROUP_P", "search_value": GROUP}
    assert schedule_request.headers["User-Agent"].startswith("university-schedule-bot/")
    assert "github.com/Shirenos/university-schedule-bot" in schedule_request.headers["User-Agent"]
    assert (schedule.min_date.isoformat(), schedule.max_date.isoformat()) == (
        "2026-08-31",
        "2026-12-27",
    )
    assert len(schedule.lessons) == len(SAMPLE_PAYLOAD)
    assert schedule.fetched_at is not None and schedule.fetched_at.tzinfo is not None


async def test_default_client_sends_polite_user_agent_and_timeout():
    client = TulguClient()
    try:
        assert client._client.headers["User-Agent"] == USER_AGENT
        assert client._client.timeout.read == 10.0
    finally:
        await client.aclose()


async def test_cache_prevents_repeated_requests_until_ttl():
    site, clock = TulguSite(), Clock()
    client = make_client(site, clock, cache_ttl=300)

    first = await client.fetch(GROUP)
    again = await client.fetch(GROUP)
    assert again is first
    assert len(site.requests) == 2  # one GetDates + one GetSchedule

    clock.now += 299
    await client.fetch(GROUP)
    assert len(site.requests) == 2

    clock.now += 2  # cache expired
    await client.fetch(GROUP)
    assert len(site.requests) == 4


async def test_force_bypasses_cache():
    site = TulguSite()
    client = make_client(site)
    await client.fetch(GROUP)
    await client.fetch(GROUP, force=True)
    assert len(site.requests) == 4


async def test_concurrent_fetches_share_one_download():
    import asyncio

    site = TulguSite()
    client = make_client(site)
    await asyncio.gather(*(client.fetch(GROUP) for _ in range(5)))
    assert len(site.requests) == 2


async def test_unknown_group_stops_after_the_cheap_dates_request():
    site = TulguSite()
    client = make_client(site)
    with pytest.raises(GroupNotFoundError, match="999999"):
        await client.fetch("999999")
    assert site.paths == ["GetDates.php"]


async def test_group_without_lessons():
    site = TulguSite()
    site.payload = []
    with pytest.raises(GroupNotFoundError):
        await make_client(site).fetch(GROUP)


async def test_invalid_group_never_hits_the_network():
    site = TulguSite()
    with pytest.raises(TulguError):
        await make_client(site).fetch("bad group!")
    assert site.requests == []


async def test_transient_errors_are_retried():
    site = TulguSite()
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503)
        if attempts["n"] == 2:
            raise httpx.ConnectTimeout("slow", request=request)
        site.fail = None  # the site recovered
        return site.handler(request)

    site.fail = flaky
    schedule = await make_client(site).fetch(GROUP)
    assert len(schedule.lessons) == len(SAMPLE_PAYLOAD)


async def test_gives_up_after_max_attempts_with_friendly_error():
    site = TulguSite()

    def always_down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    site.fail = always_down
    with pytest.raises(TulguError, match="Не удалось связаться"):
        await make_client(site).fetch(GROUP)
    assert len(site.requests) == 3


async def test_timeout_message():
    site = TulguSite()

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    site.fail = slow
    with pytest.raises(TulguError, match="время ожидания"):
        await make_client(site).fetch(GROUP)


async def test_client_errors_are_not_retried():
    site = TulguSite()
    site.status = 404
    with pytest.raises(TulguError, match="404"):
        await make_client(site).fetch(GROUP)
    assert len(site.requests) == 1


async def test_non_json_response():
    site = TulguSite()
    site.raw_body = b"<html>maintenance</html>"
    with pytest.raises(TulguError, match="не JSON"):
        await make_client(site).fetch(GROUP)


async def test_failed_download_is_not_cached():
    site = TulguSite()
    site.status = 404
    client = make_client(site)
    with pytest.raises(TulguError):
        await client.fetch(GROUP)
    site.status = 200
    assert (await client.fetch(GROUP)).lessons
