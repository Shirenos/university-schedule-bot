"""Parallel-subgroup detection and filtering of dated lessons.

Universities often run several parallel groups in the same time slot, e.g. a foreign-language
class published twice as ``Практические занятия (фр)`` and ``Практические занятия (нем)``.
A student attends only one of them, so we detect such *variant groups* and let the user
choose which variant to keep.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from schedule_bot.models import DatedLesson

ALL = "*"  # stored choice meaning "show every variant"

_SUFFIX_RE = re.compile(r"^(?P<base>.*?)\s*\((?P<suffix>[^()]+)\)\s*$")


def split_kind(kind: str) -> tuple[str, str]:
    """Split ``"Практические занятия (фр)"`` into ``("Практические занятия", "фр")``.

    A kind without a parenthesised suffix yields an empty suffix.
    """
    match = _SUFFIX_RE.match(kind.strip())
    if not match:
        return kind.strip(), ""
    return match.group("base").strip(), match.group("suffix").strip()


@dataclass(frozen=True, slots=True)
class VariantGroup:
    """A subject/kind that exists in several parallel variants."""

    subject: str
    kind: str  # kind without the parenthesised suffix
    options: tuple[str, ...]  # sorted suffixes, e.g. ("англ", "фр", "нем")

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject, self.kind)

    @property
    def token(self) -> str:
        """Short stable id that fits into Telegram callback data."""
        raw = f"{self.subject}\x00{self.kind}".encode()
        return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:8]


def detect_variant_groups(lessons: Iterable[DatedLesson]) -> list[VariantGroup]:
    """Find subject/kind pairs that have parallel entries differing only by a ``(suffix)``.

    A pair qualifies when at least one time slot (same date and time) contains two or more
    distinct suffixes. All suffixes seen for the pair anywhere in the timetable become options,
    so a subgroup that never overlaps the others in a slot (e.g. ``(англ)``) is still offered.
    """
    suffixes: dict[tuple[str, str], set[str]] = defaultdict(set)
    slots: dict[tuple[str, str, object, object, object], set[str]] = defaultdict(set)
    for lesson in lessons:
        base, suffix = split_kind(lesson.kind)
        if not suffix:
            continue
        suffixes[(lesson.subject, base)].add(suffix)
        slots[(lesson.subject, base, lesson.date, lesson.start, lesson.end)].add(suffix)

    parallel = {(subject, base) for (subject, base, *_), found in slots.items() if len(found) > 1}
    return [
        VariantGroup(subject, base, tuple(sorted(suffixes[(subject, base)])))
        for subject, base in sorted(parallel)
    ]


def pending_groups(
    groups: Iterable[VariantGroup], choices: Mapping[tuple[str, str], str]
) -> list[VariantGroup]:
    """Groups the user still has to decide on (no choice yet, or the choice is outdated)."""
    pending = []
    for group in groups:
        choice = choices.get(group.key)
        if choice is None or (choice != ALL and choice not in group.options):
            pending.append(group)
    return pending


def apply_filters(
    lessons: Iterable[DatedLesson],
    choices: Mapping[tuple[str, str], str],
) -> list[DatedLesson]:
    """Drop lessons of variants the user did not choose.

    Lessons without a suffix, and subjects without a stored choice, are always kept.
    """
    kept = []
    for lesson in lessons:
        base, suffix = split_kind(lesson.kind)
        choice = choices.get((lesson.subject, base))
        if suffix and choice is not None and choice != ALL and suffix != choice:
            continue
        kept.append(lesson)
    return kept
