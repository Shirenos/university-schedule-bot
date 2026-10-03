"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

DEFAULT_TIMEZONE = "Europe/Moscow"


class ConfigError(RuntimeError):
    """Raised when the configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_path: Path
    timezone: ZoneInfo
    semester_start: date
    log_level: str = "INFO"

    def now(self) -> datetime:
        """Current time in the configured timezone."""
        return datetime.now(self.timezone)


def default_semester_start(today: date) -> date:
    """The most recent 1 September that is not in the future."""
    year = today.year if today >= date(today.year, 9, 1) else today.year - 1
    return date(year, 9, 1)


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    """Build :class:`Settings` from the environment (and an optional .env file)."""
    load_dotenv(env_file)

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    tz_name = os.getenv("TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"Unknown TIMEZONE: {tz_name!r}") from exc

    raw_start = os.getenv("SEMESTER_START", "").strip()
    if raw_start:
        try:
            semester_start = date.fromisoformat(raw_start)
        except ValueError as exc:
            raise ConfigError(
                f"SEMESTER_START must be a date in YYYY-MM-DD format, got {raw_start!r}"
            ) from exc
    else:
        semester_start = default_semester_start(datetime.now(tz).date())

    return Settings(
        bot_token=token,
        database_path=Path(os.getenv("DATABASE_PATH", "data/schedule.db")),
        timezone=tz,
        semester_start=semester_start,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
