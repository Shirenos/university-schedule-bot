"""Visual formatting: day / week / next cards, markers, escaping and helpers."""

from datetime import date, datetime, time, timedelta

import pytest

from conftest import SEMESTER_START, at, make_dated, make_lesson
from schedule_bot.services import formatting
from schedule_bot.services.formatting import (
    format_day,
    format_day_title,
    format_duration,
    format_lesson,
    format_next,
    format_range,
    format_reminder,
    format_time_range,
    format_week,
    lesson_icon,
    plural,
    short_name,
)

MON = date(2026, 10, 5)  # SEMESTER_START is Monday 2026-09-07 -> 2026-10-05 is week 5 (odd)


def day_lessons():
    return [
        make_lesson(0, "07:45", "09:20", subject="Иностранный язык", room="9-324"),
        make_lesson(0, "09:40", "11:15", subject="Алгебра", type="seminar", room="12-313"),
        make_lesson(
            0, "11:35", "13:10", subject="История России", teacher="Чугунова Наталия Васильевна"
        ),
        make_lesson(0, "13:40", "15:15", subject="Информатика", type="lab", room="К-12"),
    ]


# --- helpers ---------------------------------------------------------------------------------


def test_date_titles_in_russian():
    assert format_day_title(MON) == "Понедельник, 5 октября"
    assert format_day_title(date(2026, 12, 31)) == "Четверг, 31 декабря"
    assert format_range(date(2026, 10, 5), date(2026, 10, 11)) == "5 – 11 октября"
    assert format_range(date(2026, 9, 28), date(2026, 10, 4)) == "28 сентября – 4 октября"


def test_time_range_uses_spaced_en_dash():
    assert format_time_range(time(9, 0), time(10, 30)) == "09:00 – 10:30"


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "1 пара"),
        (2, "2 пары"),
        (4, "4 пары"),
        (5, "5 пар"),
        (11, "11 пар"),
        (21, "21 пара"),
        (112, "112 пар"),
    ],
)
def test_plural_pairs(n, expected):
    assert plural(n, "пара", "пары", "пар") == expected


def test_short_name():
    assert short_name("Чугунова Наталия Васильевна") == "Чугунова Н. В."
    assert short_name("Иванов И. И.") == "Иванов И. И."
    assert short_name("Смит") == "Смит"
    assert short_name("O'Neil <x>") == "O'Neil <x>"


def test_duration():
    assert format_duration(timedelta(minutes=95)) == "1 ч 35 мин"
    assert format_duration(timedelta(days=2, hours=1)) == "2 д 1 ч"
    assert format_duration(timedelta(seconds=10)) == "0 мин"


def test_icons_by_lesson_type_and_language():
    assert lesson_icon(make_lesson(type="lecture")) == "📚"
    assert lesson_icon(make_lesson(type="seminar")) == "✏️"
    assert lesson_icon(make_lesson(type="lab")) == "🔬"
    assert lesson_icon(make_lesson(subject="Иностранный язык (фр)", type="seminar")) == "🌐"
    assert lesson_icon(make_lesson(subject="Английский язык")) == "🌐"
    assert lesson_icon(make_lesson(subject="Теория алгоритмов")) == "📚"


# --- lesson card -----------------------------------------------------------------------------


def test_lesson_card_layout():
    card = format_lesson(
        make_lesson(subject="История России", teacher="Чугунова Наталия Васильевна", room="Гл.-431")
    )
    lines = card.split("\n")
    assert lines[0] == "🕘 <b>09:00 – 10:30</b>"
    assert lines[1] == "📚 <b>История России</b> · лекция"
    assert lines[2] == "📍 Гл.-431 · 👤 Чугунова Н. В."


def test_lesson_card_without_room_and_teacher_has_two_lines():
    assert len(format_lesson(make_lesson(room="", teacher="")).split("\n")) == 2


def test_lesson_card_escapes_html_everywhere():
    card = format_lesson(
        make_lesson(subject="<b>x</b> & y", room="<1>", teacher="<script>alert(1)</script>")
    )
    assert "<script>" not in card and "<1>" not in card and "<b>x</b>" not in card
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in card
    assert "&lt;1&gt;" in card and "&lt;script&gt;" in card


def test_lesson_card_status_badges():
    assert "🟢 <b>идёт сейчас</b>" in format_lesson(make_lesson(), status="now")
    assert "⏭ <b>следующая</b>" in format_lesson(make_lesson(), status="next")
    done = format_lesson(make_lesson(), status="done")
    assert "<s>09:00 – 10:30</s>" in done and "✔️" in done


def test_lesson_label_override_for_practice():
    dated = make_dated(MON, subject="Алгебра", kind="Практические занятия", type="seminar")
    [lesson] = formatting.lessons_on([], MON, SEMESTER_START, [dated])
    assert "практика" in format_lesson(lesson)


# --- day view --------------------------------------------------------------------------------


def test_day_header_has_russian_date_relative_label_and_parity():
    text = format_day(MON, day_lessons(), SEMESTER_START, now=at("2026-10-05", "06:00"))
    assert text.startswith(
        "📅 <b>Понедельник, 5 октября</b>\n<i>сегодня · нечётная неделя №5</i>\n"
    )
    assert formatting.SEPARATOR in text
    tomorrow = format_day(MON, [], SEMESTER_START, now=at("2026-10-04", "12:00"))
    assert "<i>завтра · " in tomorrow
    assert "<i>послезавтра · " in format_day(MON, [], SEMESTER_START, now=at("2026-10-03"))
    assert "<i>нечётная неделя №5</i>" in format_day(MON, [], SEMESTER_START)  # no `now`


def test_day_shows_counts_and_span():
    text = format_day(MON, day_lessons(), SEMESTER_START)
    assert "📊 4 пары · с 07:45 до 15:15" in text
    assert text.index("Иностранный язык") < text.index("Алгебра") < text.index("Информатика")


def test_day_marks_now_and_next_and_done():
    text = format_day(MON, day_lessons(), SEMESTER_START, now=at("2026-10-05", "09:50"))
    # 07:45-09:20 done, 09:40-11:15 in progress, 11:35 next, 13:40 unmarked
    assert text.count("идёт сейчас") == 1 and text.count("следующая") == 1
    assert "<s>07:45 – 09:20</s>" in text
    now_pos, next_pos = text.index("идёт сейчас"), text.index("следующая")
    assert text.index("Алгебра") > now_pos and now_pos < next_pos < text.index("История")


def test_day_after_last_lesson_says_all_done():
    text = format_day(MON, day_lessons(), SEMESTER_START, now=at("2026-10-05", "20:00"))
    assert "🏁 На сегодня всё" in text and "идёт сейчас" not in text


def test_markers_only_on_the_current_day():
    text = format_day(MON, day_lessons(), SEMESTER_START, now=at("2026-10-04", "09:50"))
    assert "идёт сейчас" not in text and "следующая" not in text and "<s>" not in text


def test_empty_day_is_friendly():
    text = format_day(date(2026, 10, 4), [], SEMESTER_START, now=at("2026-10-04", "12:00"))
    assert "🌿 <b>Занятий нет</b>" in text and "Свободный день" in text
    assert "📊" not in text


# --- week view -------------------------------------------------------------------------------


def test_week_is_compact_and_lists_free_days():
    lessons = day_lessons() + [make_lesson(2, "09:40", "11:15", subject="Физика", room="Б-1")]
    text = format_week(MON, lessons, SEMESTER_START)
    assert text.startswith("🗓 <b>5 – 11 октября</b>\n<i>эта неделя · нечётная №5</i>")
    assert "🔹 <b>Пн, 5 октября</b> — <i>сегодня</i>" in text
    assert "▫️ <b>Ср, 7 октября</b>" in text
    assert "<code>09:40</code> 🔬" not in text
    assert "<code>07:45</code> 🌐 Иностранный язык · 📍9-324" in text
    assert "🌿 Свободно: Вт, Чт, Пт, Сб, Вс" in text
    assert "📊 Всего: 5 пар" in text
    # compact: one line per lesson, no teachers
    assert "👤" not in text


def test_week_of_other_week_has_relative_label_and_no_today_marker():
    lessons = day_lessons()
    nxt = format_week(MON, lessons, SEMESTER_START, week_of=MON + timedelta(days=7))
    assert "следующая неделя · чётная №6" in nxt and "сегодня" not in nxt
    prev = format_week(MON, lessons, SEMESTER_START, week_of=MON - timedelta(days=7))
    assert "прошлая неделя" in prev
    far = format_week(MON, lessons, SEMESTER_START, week_of=MON + timedelta(days=21))
    assert "<i>нечётная неделя №8" not in far  # no relative label, falls back to the plain phrase


def test_empty_week():
    text = format_week(MON, [], SEMESTER_START)
    assert "На этой неделе занятий нет" in text


def test_week_fits_into_one_message_for_a_busy_timetable():
    lessons = [
        make_lesson(
            d,
            f"{8 + i * 2:02d}:00",
            f"{9 + i * 2:02d}:30",
            subject=f"Длинное название предмета {i}",
            room="К-12",
        )
        for d in range(6)
        for i in range(5)
    ]
    assert len(format_week(MON, lessons, SEMESTER_START)) < formatting.TELEGRAM_LIMIT


# --- next, reminder, misc --------------------------------------------------------------------


def test_next_card():
    lesson = make_lesson(0, "09:00", "10:30", subject="Матан")
    text = format_next(at("2026-10-05", "09:00"), lesson, at("2026-10-05", "07:45"))
    assert text.startswith("⏭ <b>Следующая пара</b>\n<i>через 1 ч 15 мин · сегодня</i>")
    assert "Матан" in text
    later = format_next(at("2026-10-09", "09:00"), lesson, at("2026-10-05", "09:00"))
    assert "через 4 д · пятница, 9 октября" in later
    assert "· завтра" in format_next(at("2026-10-06", "09:00"), lesson, at("2026-10-05", "12:00"))


def test_reminder_message():
    text = format_reminder(make_lesson(subject="Матан", room="А-101"), 15)
    assert text.startswith("⏰ <b>Через 15 мин — пара!</b>")
    assert "Матан" in text and "А-101" in text


def test_fit_message_trims_on_line_boundary():
    text = "\n".join(f"line {i}" for i in range(2000))
    fitted = formatting.fit_message(text, limit=100)
    assert len(fitted) <= 100 and fitted.endswith("\n…")
    assert formatting.fit_message("short") == "short"


def test_week_parity_text():
    text = formatting.format_week_parity(date(2026, 10, 5), SEMESTER_START)
    assert "нечётная" in text and "№5" in text and "Следующая — чётная" in text


def test_now_is_timezone_agnostic_for_markers():
    # `now` carries a tzinfo but lessons use naive times; markers must still work.
    aware = datetime(2026, 10, 5, 9, 50, tzinfo=at("2026-10-05").tzinfo)
    assert "идёт сейчас" in format_day(MON, day_lessons(), SEMESTER_START, now=aware)
