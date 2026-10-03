from datetime import date
from zoneinfo import ZoneInfo

import pytest

from schedule_bot.config import ConfigError, load_settings

ENV_VARS = ["BOT_TOKEN", "DATABASE_PATH", "TIMEZONE", "SEMESTER_START", "LOG_LEVEL"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # set-then-delete makes monkeypatch remove anything load_dotenv() adds during a test
    for name in ENV_VARS:
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)


def write_env(tmp_path, content: str):
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_values_from_env_file(tmp_path):
    env = write_env(
        tmp_path,
        "BOT_TOKEN=123:fake\nTIMEZONE=Asia/Yekaterinburg\nSEMESTER_START=2027-02-09\nLOG_LEVEL=debug\n",
    )
    settings = load_settings(env)
    assert settings.bot_token == "123:fake"
    assert settings.timezone == ZoneInfo("Asia/Yekaterinburg")
    assert settings.semester_start == date(2027, 2, 9)
    assert settings.log_level == "DEBUG"


def test_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:fake")
    settings = load_settings(write_env(tmp_path, ""))
    assert settings.timezone == ZoneInfo("Europe/Moscow")
    assert (settings.semester_start.month, settings.semester_start.day) == (9, 1)
    assert str(settings.database_path).endswith("schedule.db")


def test_missing_token_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        load_settings(write_env(tmp_path, ""))


def test_invalid_timezone(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus")
    with pytest.raises(ConfigError, match="TIMEZONE"):
        load_settings(write_env(tmp_path, ""))


def test_invalid_semester_start(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("SEMESTER_START", "01.09.2026")
    with pytest.raises(ConfigError, match="SEMESTER_START"):
        load_settings(write_env(tmp_path, ""))
