from datetime import UTC, date, datetime

from conftest import make_dated, make_lesson
from schedule_bot.db import Database
from schedule_bot.models import DEFAULT_REMIND_MINUTES, TulguSettings


async def test_add_and_list_roundtrip(db):
    lesson_id = await db.add_lesson(
        make_lesson(2, "10:40", "12:10", subject="Физика", parity="odd")
    )
    [stored] = await db.list_lessons(1)
    assert stored.id == lesson_id
    assert (stored.weekday, stored.start.strftime("%H:%M"), stored.end.strftime("%H:%M")) == (
        2,
        "10:40",
        "12:10",
    )
    assert (stored.subject, stored.parity, stored.type) == ("Физика", "odd", "lecture")


async def test_list_is_sorted_by_weekday_then_time(db):
    await db.add_lesson(make_lesson(1, "09:00", "10:00", subject="tue"))
    await db.add_lesson(make_lesson(0, "13:00", "14:00", subject="mon-late"))
    await db.add_lesson(make_lesson(0, "08:00", "09:00", subject="mon-early"))
    assert [lesson.subject for lesson in await db.list_lessons(1)] == [
        "mon-early",
        "mon-late",
        "tue",
    ]


async def test_schedules_are_isolated_per_user(db):
    await db.add_lesson(make_lesson(user_id=1, subject="mine"))
    await db.add_lesson(make_lesson(user_id=2, subject="theirs"))
    assert [lesson.subject for lesson in await db.list_lessons(1)] == ["mine"]
    assert await db.count_lessons(2) == 1


async def test_delete_only_own_lessons(db):
    lesson_id = await db.add_lesson(make_lesson(user_id=1))
    assert await db.delete_lesson(2, lesson_id) is False
    assert await db.count_lessons(1) == 1
    assert await db.delete_lesson(1, lesson_id) is True
    assert await db.delete_lesson(1, lesson_id) is False
    assert await db.list_lessons(1) == []


async def test_add_lessons_bulk(db):
    stored = await db.add_lessons([make_lesson(i) for i in range(5)])
    assert stored == 5
    assert await db.count_lessons(1) == 5


async def test_reminder_defaults_and_upsert(db):
    default = await db.get_reminder(1)
    assert (default.enabled, default.minutes) == (False, DEFAULT_REMIND_MINUTES)
    await db.set_reminder(1, True, 30)
    await db.set_reminder(1, True, 45)
    current = await db.get_reminder(1)
    assert (current.enabled, current.minutes) == (True, 45)


async def test_list_reminder_users_only_enabled(db):
    await db.set_reminder(1, True, 15)
    await db.set_reminder(2, False, 15)
    await db.set_reminder(3, True, 5)
    assert sorted(await db.list_reminder_users()) == [1, 3]


async def test_data_persists_across_reconnect(tmp_path):
    path = tmp_path / "persist.db"
    first = Database(path)
    await first.connect()
    await first.add_lesson(make_lesson(subject="persisted"))
    await first.set_reminder(1, True, 20)
    await first.close()

    second = Database(path)
    await second.connect()
    try:
        assert [lesson.subject for lesson in await second.list_lessons(1)] == ["persisted"]
        assert (await second.get_reminder(1)).minutes == 20
    finally:
        await second.close()


# --- dated lessons / TulSU / filters ---------------------------------------------------------


async def test_dated_lessons_roundtrip_and_replace(db):
    day = date(2026, 9, 2)
    first = [
        make_dated(day, "09:00", "10:30", subject="B", kind="Практические занятия (фр)"),
        make_dated(day, "07:45", "09:20", subject="A"),
    ]
    assert await db.replace_dated_lessons(1, first) == 2
    stored = await db.list_dated_lessons(1)
    assert [lesson.subject for lesson in stored] == ["A", "B"]  # sorted by date, start
    assert stored[1].kind == "Практические занятия (фр)"
    assert (stored[0].date, stored[0].group, stored[0].type) == (day, "221461", "lecture")
    assert await db.count_dated_lessons(1) == 2

    await db.replace_dated_lessons(1, [make_dated(day, subject="only")])
    assert [lesson.subject for lesson in await db.list_dated_lessons(1)] == ["only"]


async def test_dated_lessons_are_per_user(db):
    day = date(2026, 9, 2)
    await db.replace_dated_lessons(1, [make_dated(day, subject="mine", user_id=1)])
    await db.replace_dated_lessons(2, [make_dated(day, subject="theirs", user_id=2)])
    await db.replace_dated_lessons(1, [])
    assert await db.count_dated_lessons(1) == 0
    assert [lesson.subject for lesson in await db.list_dated_lessons(2)] == ["theirs"]


async def test_clear_dated_lessons(db):
    await db.replace_dated_lessons(1, [make_dated(date(2026, 9, 2))])
    await db.clear_dated_lessons(1)
    assert await db.count_dated_lessons(1) == 0


async def test_tulgu_settings_roundtrip(db):
    assert await db.get_tulgu(1) is None
    synced = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    await db.set_tulgu(1, TulguSettings("221461", synced, date(2026, 8, 31), date(2026, 12, 27)))
    stored = await db.get_tulgu(1)
    assert stored == TulguSettings("221461", synced, date(2026, 8, 31), date(2026, 12, 27))
    await db.set_tulgu(1, TulguSettings("221462"))
    assert (await db.get_tulgu(1)) == TulguSettings("221462", None, None, None)


async def test_filters_upsert_and_clear(db):
    assert await db.get_filters(1) == {}
    await db.set_filter(1, "Иностранный язык", "Практические занятия", "фр")
    await db.set_filter(1, "Иностранный язык", "Практические занятия", "нем")
    await db.set_filter(2, "Иностранный язык", "Практические занятия", "фр")
    assert await db.get_filters(1) == {("Иностранный язык", "Практические занятия"): "нем"}
    await db.clear_filters(1)
    assert await db.get_filters(1) == {}
    assert len(await db.get_filters(2)) == 1
