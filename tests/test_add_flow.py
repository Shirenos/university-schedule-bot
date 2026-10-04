"""End-to-end tests of /add, /import and other commands via the shared Telegram test harness."""

from __future__ import annotations


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
    assert "Справка" in session.texts[-1]
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
    assert "Ближайших занятий нет" in session.texts[-1]


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
