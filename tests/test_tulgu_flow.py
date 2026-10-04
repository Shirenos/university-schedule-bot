"""End-to-end ТулГУ scenarios: commands -> mocked tulsu.ru -> SQLite -> views."""

from __future__ import annotations

import httpx
from aiogram.methods import AnswerCallbackQuery

from conftest import at, make_lesson
from schedule_bot.models import TulguSettings
from schedule_bot.services.sync import SyncService
from schedule_bot.services.tulgu import TulguClient
from tulgu_data import GROUP, SAMPLE_PAYLOAD, TulguSite


def button(app, text: str) -> str:
    """callback_data of the button labelled ``text`` in the most recent keyboard."""
    for row in app.session.keyboards[-1].inline_keyboard:
        for item in row:
            if item.text == text:
                return item.callback_data
    raise AssertionError(f"no button {text!r}")


async def connect_and_choose(app, variant: str = "фр") -> None:
    await app.say(f"/tulgu {GROUP}")
    await app.press(button(app, variant))


async def test_tulgu_without_args_shows_usage_then_saved_group(app, db):
    await app.say("/tulgu")
    assert "/tulgu 221461" in app.session.texts[-1]
    assert app.site.requests == []

    await app.say(f"/tulgu {GROUP}")
    await app.say("/tulgu")
    saved = app.session.texts[-1]
    assert GROUP in saved and "Занятий загружено: <b>8</b>" in saved
    assert "31.08.2026 – 27.12.2026" in saved
    assert "/sync" in saved


async def test_first_sync_stores_lessons_and_asks_which_subgroup(app, db):
    await app.say(f"/tulgu {GROUP}")

    texts = app.session.texts
    assert "Загружаю расписание группы 221461" in texts[0]
    assert "Расписание загружено" in texts[1] and "Занятий загружено: <b>8</b>" in texts[1]
    assert "параллельные подгруппы" in texts[2]
    assert "Иностранный язык" in texts[3] and "Практические занятия" in texts[3]

    options = [b.text for row in app.session.keyboards[-1].inline_keyboard for b in row]
    assert options == ["англ", "нем", "фр", "Показывать все"]
    assert all(
        len(b.callback_data.encode()) <= 64
        for row in app.session.keyboards[-1].inline_keyboard
        for b in row
    )
    assert await db.count_dated_lessons(app.user_id) == len(SAMPLE_PAYLOAD)
    assert (await db.get_tulgu(app.user_id)).group == GROUP
    app.scheduler.reschedule.assert_called_with(app.user_id)


async def test_choosing_a_subgroup_filters_all_views(app, db):
    await connect_and_choose(app, "фр")
    assert "оставляю «фр»" in app.session.edits[-1]
    assert await db.get_filters(app.user_id) == {("Иностранный язык", "Практические занятия"): "фр"}

    app.set_now(at("2026-09-02", "06:00"))
    await app.say("/today")
    today = app.session.texts[-1]
    assert "Иностранный язык (фр)" in today and "Кондратьева" in today
    assert "(нем)" not in today and "Преподаватель Немецкий" not in today
    assert "История России" in today
    assert today.index("Иностранный язык") < today.index("История России")

    await app.say("/tomorrow")
    assert "Занятий нет" in app.session.texts[-1]  # nothing on 03.09

    await app.say("/week")
    week = app.session.texts[-1]
    assert "Иностранный язык (фр)" in week and "Иностранный язык (англ)" not in week
    assert "сегодня" in week

    app.set_now(at("2026-09-02", "10:00"))
    await app.say("/next")
    assert "История России" in app.session.texts[-1]
    assert "через 1 ч 35 мин" in app.session.texts[-1]


async def test_german_choice_shows_the_other_teacher(app, db):
    await connect_and_choose(app, "нем")
    app.set_now(at("2026-09-02", "06:00"))
    await app.say("/today")
    today = app.session.texts[-1]
    assert "Иностранный язык (нем)" in today and "Преподаватель Немецкий" in today
    assert "Кондратьева" not in today


async def test_show_all_variants(app, db):
    await connect_and_choose(app, "Показывать все")
    assert "показываю все варианты" in app.session.edits[-1]
    app.set_now(at("2026-09-02", "06:00"))
    await app.say("/today")
    today = app.session.texts[-1]
    assert "(фр)" in today and "(нем)" in today


async def test_manual_weekly_lessons_are_merged_without_duplicates(app, db):
    await connect_and_choose(app, "фр")
    uid = app.user_id
    # 02.09.2026 is a Wednesday. One manual lesson duplicates a synced one, one is extra.
    await db.add_lesson(
        make_lesson(2, "11:35", "13:10", subject="история россии", user_id=uid, room="manual")
    )
    await db.add_lesson(make_lesson(2, "17:30", "19:00", subject="Секция", user_id=uid))
    app.set_now(at("2026-09-02", "06:00"))
    await app.say("/today")
    today = app.session.texts[-1]
    assert today.count("России") + today.count("россии") == 1
    assert "Гл.-431" in today and "manual" not in today  # the synced entry won
    assert "Секция" in today


async def test_sync_uses_cache_and_does_not_ask_again(app, db):
    await connect_and_choose(app, "фр")
    requests_before = len(app.site.requests)
    sent_before = len(app.session.texts)

    await app.say("/sync")
    texts = app.session.texts[sent_before:]
    assert any("из кэша" in text for text in texts)
    assert not any("параллельные подгруппы" in text for text in texts)
    assert len(app.site.requests) == requests_before
    assert await db.get_filters(app.user_id)  # the choice survived the refresh


async def test_sync_refreshes_changed_data(app, db):
    await connect_and_choose(app, "фр")
    app.site.payload = [SAMPLE_PAYLOAD[2]]  # the site now publishes only one lesson
    # Expire the client's cache by moving time on.
    app.sync_service._client._clock = lambda: 10**9
    await app.say("/sync")
    assert await db.count_dated_lessons(app.user_id) == 1
    assert "Занятий загружено: <b>1</b>" in app.session.texts[-1]


async def test_sync_without_group(app, db):
    await app.say("/sync")
    assert "Группа не выбрана" in app.session.texts[-1]


async def test_unknown_group_and_bad_input(app, db):
    await app.say("/tulgu 999999")
    assert "не найдена" in app.session.texts[-1]
    assert await db.get_tulgu(app.user_id) is None
    await app.say("/tulgu <script>")
    assert "Некорректный номер группы" in app.session.texts[-1]
    assert [p for p in app.site.paths] == ["GetDates.php"]  # only the unknown group was queried


async def test_site_failure_keeps_previous_data(app, db):
    await connect_and_choose(app, "фр")
    app.sync_service._client._clock = lambda: 10**9  # expire cache

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    app.site.fail = down
    await app.say("/sync")
    assert "Не удалось связаться с сайтом ТулГУ" in app.session.texts[-1]
    assert await db.count_dated_lessons(app.user_id) == len(SAMPLE_PAYLOAD)


async def test_filters_command_lets_you_change_the_choice(app, db):
    await app.say("/filters")
    assert "Сначала подключите" in app.session.texts[-1]

    await connect_and_choose(app, "фр")
    await app.say("/filters")
    assert "Иностранный язык (Практические занятия): <b>фр</b>" in app.session.texts[-2]
    await app.press(button(app, "нем"))
    assert await db.get_filters(app.user_id) == {
        ("Иностранный язык", "Практические занятия"): "нем"
    }
    assert app.scheduler.reschedule.call_count >= 3


async def test_filters_when_there_are_no_parallel_groups(app, db):
    app.site.payload = [SAMPLE_PAYLOAD[2], SAMPLE_PAYLOAD[6]]
    await app.say(f"/tulgu {GROUP}")
    assert not any("параллельные" in text for text in app.session.texts)
    await app.say("/filters")
    assert "нет параллельных подгрупп" in app.session.texts[-1]


async def test_stale_filter_button_is_rejected(app, db):
    await app.say(f"/tulgu {GROUP}")
    await app.press("flt:deadbeef:0")
    assert isinstance(app.session.calls[-1], AnswerCallbackQuery)
    assert app.session.calls[-1].show_alert is True
    assert await db.get_filters(app.user_id) == {}


async def test_list_mentions_synced_lessons(app, db):
    await app.say(f"/tulgu {GROUP}")
    await app.say("/list")
    assert "группа 221461" in app.session.texts[-1]


async def test_changing_group_resets_filters(db):
    site = TulguSite()
    service = SyncService(db, TulguClient(client=site.client()))
    await db.set_tulgu(1, TulguSettings("OLD"))
    await db.set_filter(1, "Иностранный язык", "Практические занятия", "фр")
    result = await service.sync(1, GROUP)
    assert await db.get_filters(1) == {}
    assert [g.subject for g in result.pending] == ["Иностранный язык"]
    assert (await db.get_tulgu(1)).group == GROUP
