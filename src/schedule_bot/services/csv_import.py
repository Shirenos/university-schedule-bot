"""Import a schedule from a CSV file.

Expected header: ``weekday,start,end,subject,type,room,teacher,parity``.
``room``, ``teacher`` and ``parity`` may be empty (parity defaults to ``every``).
Both ``,`` and ``;`` delimiters are accepted, as are UTF-8 (with BOM) and Windows-1251 files.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from schedule_bot.models import Lesson
from schedule_bot.services.parsing import (
    ParseError,
    ensure_ordered,
    parse_parity,
    parse_time,
    parse_type,
    parse_weekday,
)

REQUIRED_COLUMNS = ("weekday", "start", "end", "subject", "type")
OPTIONAL_COLUMNS = ("room", "teacher", "parity")
MAX_FILE_SIZE = 256 * 1024
MAX_FIELD_LENGTH = 200


class CsvImportError(ValueError):
    """The file as a whole is unusable (bad encoding, missing columns, ...)."""


@dataclass(slots=True)
class ImportResult:
    lessons: list[Lesson] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)  # (line number, message)


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvImportError("Не удалось определить кодировку файла (нужна UTF-8 или Windows-1251).")


def _cell(row: dict[str, str | None], key: str) -> str:
    return (row.get(key) or "").strip()


def parse_csv(text: str, user_id: int) -> ImportResult:
    """Parse CSV text into lessons; invalid rows are reported in ``errors`` and skipped."""
    header = text.split("\n", 1)[0]
    delimiter = ";" if header.count(";") > header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise CsvImportError("Файл пустой.")
    reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
    missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise CsvImportError("Не хватает колонок: " + ", ".join(missing))

    result = ImportResult()
    for row in reader:
        line = reader.line_num
        try:
            subject = _cell(row, "subject")
            if not subject:
                raise ParseError("пустое название предмета")
            room, teacher = _cell(row, "room"), _cell(row, "teacher")
            if max(len(subject), len(room), len(teacher)) > MAX_FIELD_LENGTH:
                raise ParseError("слишком длинное значение")
            start, end = parse_time(_cell(row, "start")), parse_time(_cell(row, "end"))
            ensure_ordered(start, end)
            result.lessons.append(
                Lesson(
                    user_id=user_id,
                    weekday=parse_weekday(_cell(row, "weekday")),
                    start=start,
                    end=end,
                    subject=subject,
                    type=parse_type(_cell(row, "type")),
                    room=room,
                    teacher=teacher,
                    parity=parse_parity(_cell(row, "parity")),
                )
            )
        except ParseError as exc:
            result.errors.append((line, str(exc)))
    return result


def parse_csv_bytes(data: bytes, user_id: int) -> ImportResult:
    if len(data) > MAX_FILE_SIZE:
        raise CsvImportError("Файл слишком большой (максимум 256 КБ).")
    return parse_csv(decode(data), user_id)
