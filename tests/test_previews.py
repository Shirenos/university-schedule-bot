"""The preview generator must keep working with the bot's real templates (no Chrome needed)."""

from __future__ import annotations

import importlib.util
import sys
from html import escape
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_previews.py"


def load():
    spec = importlib.util.spec_from_file_location("make_previews", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_demo_page_uses_real_templates():
    mp = load()
    dated = mp.demo_lessons()
    assert dated
    assert all(d.date.weekday() < 5 for d in dated)
    text = mp.formatting.format_day(mp.TODAY, [], mp.SEMESTER_START, dated, now=mp.NOW)
    assert "идёт сейчас" in text and "следующая" in text
    week = mp.formatting.format_week(mp.TODAY, [], mp.SEMESTER_START, dated)
    assert "Свободно: Сб, Вс" in week
    html = mp.page([mp.Msg(text, buttons=mp.buttons(mp.keyboards.day_nav(mp.TODAY)))], mp.menu())
    assert escape(mp.CAPTION) in html
    assert "<!doctype html>" in html
