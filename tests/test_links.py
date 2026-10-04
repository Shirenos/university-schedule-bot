"""Links in lesson cards: rooms -> building on the map, teachers -> tulsu.ru schedule search."""

import json
import tomllib
from datetime import date
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from aiogram.client.default import Default

from conftest import SEMESTER_START, FakeSession, make_dated, make_lesson
from schedule_bot.main import create_bot
from schedule_bot.services.formatting import format_lesson, format_lesson_line, link
from schedule_bot.services.links import load_building_map, parse_buildings, room_url, teacher_url
from schedule_bot.services.schedule import dated_as_lesson, lessons_on


def map_query(url: str) -> str:
    parsed = urlparse(url)
    assert parsed.scheme == "https" and parsed.netloc == "yandex.ru" and parsed.path == "/maps/"
    return parse_qs(parsed.query)["text"][0]


# --- config file -------------------------------------------------------------------------------


def test_config_file_is_packaged_and_well_formed():
    text = (resources.files("schedule_bot") / "data" / "tulgu_buildings.toml").read_text("utf-8")
    data = tomllib.loads(text)
    assert data["building"], "no buildings configured"
    for entry in data["building"]:
        assert entry["address"].startswith("Тула, ")
        page = urlparse(entry["page"])
        assert page.scheme == "https" and page.netloc == "tulsu.ru"
        assert page.path.startswith("/facilities/academic-building/")
        assert entry["name"]


def test_pyproject_ships_the_config_file():
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text("utf-8")
    assert "data/*.toml" in pyproject


def test_parse_rejects_bad_config():
    ok = {"map_url": "https://m.example/?q={query}", "building": [{"prefixes": ["A"]}]}
    parse_buildings(ok)
    with pytest.raises(ValueError):
        parse_buildings({**ok, "map_url": "http://insecure/?q={query}"})
    with pytest.raises(ValueError):
        parse_buildings({**ok, "map_url": "https://m.example/"})
    with pytest.raises(ValueError):
        parse_buildings({**ok, "building": [{"prefixes": []}]})
    with pytest.raises(ValueError):
        parse_buildings({**ok, "building": [{"prefixes": ["A"]}, {"prefixes": ["a"]}]})
    with pytest.raises(ValueError):
        parse_buildings({**ok, "building": [{"prefixes": ["A-1"]}]})


def test_custom_building_is_picked_up_without_code_changes():
    bmap = parse_buildings(
        {
            "map_url": "https://m.example/?q={query}",
            "building": [{"prefixes": ["Х"], "address": "Тула, ул. Тестовая, 1&2"}],
        }
    )
    assert (
        bmap.room_url("х-101")
        == "https://m.example/?q=%D0%A2%D1%83%D0%BB%D0%B0%2C%20%D1%83%D0%BB.%20%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D0%B0%D1%8F%2C%201%262"
    )


# --- rooms -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("room", "address"),
    [
        ("Гл.-402", "Тула, проспект Ленина, 92"),
        ("гл.-402", "Тула, проспект Ленина, 92"),
        ("  Гл.-402 ", "Тула, проспект Ленина, 92"),
        ("1-101", "Тула, проспект Ленина, 95"),
        ("9-324", "Тула, проспект Ленина, 92"),
        ("3-206", "Тула, проспект Ленина, 84, корпус 8"),
        ("12-313", "Тула, улица Агеева, 1Б"),
        ("10-1", "Тула, улица Болдина, 128"),
        ("6лаб-101", "Тула, улица Смидович, 3А"),
        ("6-201", "Тула, проспект Ленина, 90"),
    ],
)
def test_known_buildings_link_to_the_map(room, address):
    url = room_url(room)
    assert url is not None
    assert map_query(url) == address
    assert url.isascii() and " " not in url


@pytest.mark.parametrize(
    "room",
    [
        "",
        "101",  # no building prefix
        "Гл.",  # no room number
        "Гл.-",
        "-402",
        "13-101",  # УК №13: the site publishes no address
        "15-101",
        "16-101",
        "19-1-101",  # must not be read as building 1
        "УПК 19-203",
        "КБП-5",
        "Спорткорп-1",
        "Дистанционно",
        "Без аудитории",
        "ГУЗ ТОКБ-1",
        "<script>-1",
        "Б-1",
    ],
)
def test_unknown_rooms_have_no_link(room):
    assert room_url(room) is None


def test_prefixes_are_unique_and_never_contain_a_dash():
    seen = set()
    for building in load_building_map().buildings:
        for prefix in building.prefixes:
            assert "-" not in prefix
            assert prefix.casefold() not in seen
            seen.add(prefix.casefold())


# --- teachers ----------------------------------------------------------------------------------


def test_teacher_url_points_to_the_schedule_search():
    url = teacher_url("Чугунова Наталия Васильевна")
    parsed = urlparse(url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == ("https", "tulsu.ru", "/schedule/")
    assert parse_qs(parsed.query) == {"search": ["Чугунова Наталия Васильевна"]}
    assert url.isascii() and " " not in url


def test_teacher_url_normalises_whitespace_and_encodes_specials():
    assert teacher_url("  Иванов   Иван ") == teacher_url("Иванов Иван")
    assert unquote(teacher_url("A&B=C#D?")) == "https://tulsu.ru/schedule/?search=A&B=C#D?"
    assert "&B" not in teacher_url("A&B")
    assert teacher_url("") is None and teacher_url("   ") is None


# --- cards -------------------------------------------------------------------------------------


def test_link_helper_escapes_text_and_url():
    assert link("a<b>&", None) == "a&lt;b&gt;&amp;"
    assert link("a<b>", "") == "a&lt;b&gt;"
    assert (
        link("x", 'https://e.x/?a=1&b="2"')
        == '<a href="https://e.x/?a=1&amp;b=&quot;2&quot;">x</a>'
    )


def test_card_links_room_and_university_teacher():
    lesson = dated_as_lesson(
        make_dated(
            date(2026, 10, 5),
            room="Гл.-402",
            teacher="Чугунова Наталия Васильевна",
            subject="История",
        )
    )
    details = format_lesson(lesson).split("\n")[2]
    room_href = room_url("Гл.-402")
    teacher_href = teacher_url("Чугунова Наталия Васильевна")
    assert details == (
        f'📍 <a href="{room_href}">Гл.-402</a> · 👤 <a href="{teacher_href}">Чугунова Н. В.</a>'
    )
    assert (
        "https://tulsu.ru/schedule/?search=%D0%A7%D1%83%D0%B3%D1%83%D0%BD%D0%BE%D0%B2%D0%B0"
        in details
    )


def test_merged_dated_lessons_carry_the_teacher_link():
    day = date(2026, 10, 5)
    lessons = lessons_on([], day, SEMESTER_START, [make_dated(day, teacher="Петров Пётр Петрович")])
    assert lessons[0].teacher_url == teacher_url("Петров Пётр Петрович")


def test_manual_lessons_keep_the_teacher_as_plain_text():
    lesson = make_lesson(room="Гл.-402", teacher="Иванов Иван Иванович")
    assert lesson.teacher_url == ""
    details = format_lesson(lesson).split("\n")[2]
    assert details.endswith("👤 Иванов И. И.")
    assert details.count("<a ") == 1  # only the room


def test_unknown_room_and_missing_teacher_are_plain_text():
    card = format_lesson(make_lesson(room="Дистанционно", teacher=""))
    assert card.endswith("📍 Дистанционно")
    assert "<a " not in card
    card = format_lesson(dated_as_lesson(make_dated(date(2026, 10, 5), room="", teacher="")))
    assert "<a " not in card and len(card.split("\n")) == 2


def test_hostile_text_is_escaped_inside_links():
    lesson = dated_as_lesson(
        make_dated(
            date(2026, 10, 5),
            room="Гл.-<b>&\"'",
            teacher='Ив<script> "Иван" & Ко',
            subject="<i>x</i>",
        )
    )
    card = format_lesson(lesson)
    assert "<script" not in card and "-<b>" not in card and "<i>x" not in card
    assert "Гл.-&lt;b&gt;&amp;&quot;&#x27;</a>" in card
    # every href is a clean https URL without raw quotes or angle brackets
    hrefs = [part.split('"', 1)[0] for part in card.split('href="')[1:]]
    assert hrefs and all(h.startswith("https://") and "<" not in h and " " not in h for h in hrefs)


def test_week_line_links_the_room():
    line = format_lesson_line(make_lesson(room="Гл.-402"))
    assert f'📍<a href="{room_url("Гл.-402")}">Гл.-402</a>' in line
    assert "<a " not in format_lesson_line(make_lesson(room="Дистанционно"))


# --- link previews -----------------------------------------------------------------------------


def test_link_previews_are_disabled_by_default():
    bot = create_bot("123456:TEST-TOKEN-NOT-REAL", session=FakeSession())
    assert bot.default.link_preview_is_disabled is True
    assert bot.default.parse_mode == "HTML"
    options = bot.session.prepare_value(Default("link_preview"), bot, {})
    assert json.loads(options) == {"is_disabled": True}
