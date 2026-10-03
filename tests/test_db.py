from conftest import make_lesson
from schedule_bot.db import Database
from schedule_bot.models import DEFAULT_REMIND_MINUTES


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
