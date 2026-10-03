from pathlib import Path

import pytest

from schedule_bot.services.csv_import import (
    MAX_FILE_SIZE,
    CsvImportError,
    parse_csv,
    parse_csv_bytes,
)

HEADER = "weekday,start,end,subject,type,room,teacher,parity\n"
EXAMPLE = Path(__file__).parent.parent / "examples" / "schedule.csv"


def test_example_file_is_valid():
    result = parse_csv_bytes(EXAMPLE.read_bytes(), user_id=7)
    assert result.errors == []
    assert len(result.lessons) == 11
    assert {lesson.user_id for lesson in result.lessons} == {7}


def test_parses_all_fields():
    result = parse_csv(HEADER + "mon,09:00,10:30,Math,lecture,A-101,Ivanov,odd\n", user_id=1)
    assert result.errors == []
    lesson = result.lessons[0]
    assert (lesson.weekday, lesson.start.hour, lesson.end.minute) == (0, 9, 30)
    assert (lesson.subject, lesson.type, lesson.room, lesson.teacher, lesson.parity) == (
        "Math",
        "lecture",
        "A-101",
        "Ivanov",
        "odd",
    )


def test_optional_values_may_be_empty():
    result = parse_csv(HEADER + "3,9:00,10:30,Physics,lab,,,\n", user_id=1)
    lesson = result.lessons[0]
    assert (lesson.weekday, lesson.room, lesson.teacher, lesson.parity) == (2, "", "", "every")


def test_russian_aliases():
    text = (
        HEADER
        + "Пн,09:00,10:30,Матан,Лекция,101,Иванов,нечётная\nпятница,10:00,11:30,Х,лаб,,,чет\n"
    )
    first, second = parse_csv(text, 1).lessons
    assert (first.weekday, first.type, first.parity) == (0, "lecture", "odd")
    assert (second.weekday, second.type, second.parity) == (4, "lab", "even")


def test_semicolon_delimiter_and_bom():
    text = "\ufeff" + HEADER.replace(",", ";") + "tue;09:00;10:30;Art;seminar;1;T;every\n"
    result = parse_csv_bytes(text.encode("utf-8"), 1)
    assert len(result.lessons) == 1
    assert result.lessons[0].weekday == 1


def test_windows_1251_file():
    text = HEADER + "пн,09:00,10:30,Физика,лекция,1,Петров,every\n"
    result = parse_csv_bytes(text.encode("cp1251"), 1)
    assert result.lessons[0].subject == "Физика"


def test_bad_rows_are_reported_and_good_rows_kept():
    text = HEADER + (
        "mon,09:00,10:30,Good,lecture,,,\n"
        "xyz,09:00,10:30,BadDay,lecture,,,\n"
        "mon,25:00,26:00,BadTime,lecture,,,\n"
        "mon,11:00,10:00,Backwards,lecture,,,\n"
        "mon,09:00,10:30,,lecture,,,\n"
        "mon,09:00,10:30,BadType,exam,,,\n"
        "mon,09:00,10:30,BadParity,lab,,,sometimes\n"
    )
    result = parse_csv(text, 1)
    assert [lesson.subject for lesson in result.lessons] == ["Good"]
    assert [line for line, _ in result.errors] == [3, 4, 5, 6, 7, 8]


def test_missing_columns():
    with pytest.raises(CsvImportError, match="subject"):
        parse_csv("weekday,start,end,type\nmon,09:00,10:00,lecture\n", 1)


def test_empty_file():
    with pytest.raises(CsvImportError):
        parse_csv("", 1)


def test_header_case_and_spaces_are_ignored():
    text = " Weekday , START,end,Subject,type\nmon,09:00,10:00,X,lecture\n"
    assert len(parse_csv(text, 1).lessons) == 1


def test_file_too_large():
    with pytest.raises(CsvImportError):
        parse_csv_bytes(b"x" * (MAX_FILE_SIZE + 1), 1)
