from datetime import date, time

from conftest import make_dated
from schedule_bot.services.filters import (
    ALL,
    VariantGroup,
    apply_filters,
    detect_variant_groups,
    pending_groups,
    split_kind,
)
from schedule_bot.services.tulgu import parse_lessons
from tulgu_data import GROUP, SAMPLE_PAYLOAD, entry


def test_split_kind():
    assert split_kind("Практические занятия (фр)") == ("Практические занятия", "фр")
    assert split_kind("Практические занятия(нем) ") == ("Практические занятия", "нем")
    assert split_kind("Лекции") == ("Лекции", "")
    assert split_kind("") == ("", "")


def sample():
    return parse_lessons(SAMPLE_PAYLOAD, GROUP)


def test_detects_parallel_french_german_and_includes_english_option():
    [group] = detect_variant_groups(sample())
    assert group.subject == "Иностранный язык"
    assert group.kind == "Практические занятия"
    assert group.options == ("англ", "нем", "фр")  # англ never overlaps, but is still offered


def test_no_group_without_a_shared_slot():
    lessons = [
        make_dated(date(2026, 9, 2), "08:00", "09:00", kind="Практические занятия (фр)"),
        make_dated(date(2026, 9, 3), "08:00", "09:00", kind="Практические занятия (нем)"),
    ]
    assert detect_variant_groups(lessons) == []


def test_same_suffix_twice_is_not_a_variant():
    lessons = [
        make_dated(date(2026, 9, 2), "08:00", "09:00", kind="Лекции (поток)", room="1"),
        make_dated(date(2026, 9, 2), "08:00", "09:00", kind="Лекции (поток)", room="2"),
    ]
    assert detect_variant_groups(lessons) == []


def test_different_subjects_in_one_slot_are_not_variants():
    lessons = [
        make_dated(date(2026, 9, 2), "08:00", "09:00", subject="A", kind="Практика (1)"),
        make_dated(date(2026, 9, 2), "08:00", "09:00", subject="B", kind="Практика (2)"),
    ]
    assert detect_variant_groups(lessons) == []


def test_multiple_independent_variant_groups_sorted():
    lessons = [
        make_dated(date(2026, 9, 2), "08:00", "09:00", subject="Физика", kind="Лабораторные (1)"),
        make_dated(date(2026, 9, 2), "08:00", "09:00", subject="Физика", kind="Лабораторные (2)"),
        make_dated(date(2026, 9, 2), "10:00", "11:00", subject="Английский", kind="Практика (а)"),
        make_dated(date(2026, 9, 2), "10:00", "11:00", subject="Английский", kind="Практика (б)"),
    ]
    assert [g.subject for g in detect_variant_groups(lessons)] == ["Английский", "Физика"]


def test_token_is_short_and_stable():
    group = VariantGroup("Иностранный язык", "Практические занятия", ("фр", "нем"))
    assert len(group.token) == 8
    assert group.token == VariantGroup(group.subject, group.kind, ()).token
    assert f"flt:{group.token}:2".encode().__len__() <= 64


def test_pending_groups():
    [group] = detect_variant_groups(sample())
    assert pending_groups([group], {}) == [group]
    assert pending_groups([group], {group.key: "фр"}) == []
    assert pending_groups([group], {group.key: ALL}) == []
    assert pending_groups([group], {group.key: "исп"}) == [group]  # outdated choice


def test_apply_filters_keeps_only_chosen_variant():
    lessons = sample()
    [group] = detect_variant_groups(lessons)
    kept = apply_filters(lessons, {group.key: "фр"})
    kinds = [lesson.kind for lesson in kept]
    assert "Практические занятия (фр)" in kinds
    assert not any("(нем)" in kind or "(англ)" in kind for kind in kinds)
    # unrelated lessons survive
    assert {"Лекции", "Лабораторные занятия"} <= set(kinds)
    assert len(kept) == len(lessons) - 3  # two (нем) and one (англ) entry dropped


def test_apply_filters_all_and_no_choice_keep_everything():
    lessons = sample()
    [group] = detect_variant_groups(lessons)
    assert apply_filters(lessons, {}) == lessons
    assert apply_filters(lessons, {group.key: ALL}) == lessons


def test_unsuffixed_lessons_are_never_filtered():
    plain = parse_lessons(
        [
            entry(
                "02.09.2026", "07:45 - 09:20", "Иностранный язык", "Практические занятия", "1", "T"
            )
        ],
        GROUP,
    )
    choices = {("Иностранный язык", "Практические занятия"): "фр"}
    assert apply_filters(plain, choices) == plain
    assert time(7, 45) == plain[0].start
