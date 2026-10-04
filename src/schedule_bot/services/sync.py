"""Glue between the ТулГУ client and the database: sync a user's group and report what changed."""

from __future__ import annotations

from dataclasses import dataclass, replace

from schedule_bot.db import Database
from schedule_bot.models import TulguSettings
from schedule_bot.services.filters import VariantGroup, detect_variant_groups, pending_groups
from schedule_bot.services.tulgu import TulguClient


@dataclass(frozen=True, slots=True)
class SyncResult:
    settings: TulguSettings
    lessons: int
    from_cache: bool
    pending: list[VariantGroup]  # parallel groups the user still has to choose a variant for


class SyncService:
    def __init__(self, db: Database, client: TulguClient) -> None:
        self._db = db
        self._client = client

    async def sync(self, user_id: int, group: str, *, force: bool = False) -> SyncResult:
        """Download ``group``'s timetable and store it for ``user_id``.

        Raises :class:`~schedule_bot.services.tulgu.TulguError` (with a user-facing message)
        and leaves previously stored data untouched when the download fails.
        """
        group = group.strip()
        from_cache = not force and self._client.cached(group) is not None
        schedule = await self._client.fetch(group, force=force)

        previous = await self._db.get_tulgu(user_id)
        if previous is not None and previous.group != group:
            await self._db.clear_filters(user_id)  # choices belong to the old group

        lessons = [replace(lesson, user_id=user_id) for lesson in schedule.lessons]
        await self._db.replace_dated_lessons(user_id, lessons)
        settings = TulguSettings(
            group=group,
            synced_at=schedule.fetched_at,
            min_date=schedule.min_date,
            max_date=schedule.max_date,
        )
        await self._db.set_tulgu(user_id, settings)

        groups = detect_variant_groups(lessons)
        pending = pending_groups(groups, await self._db.get_filters(user_id))
        return SyncResult(settings, len(lessons), from_cache, pending)

    async def variant_groups(self, user_id: int) -> list[VariantGroup]:
        return detect_variant_groups(await self._db.list_dated_lessons(user_id))
