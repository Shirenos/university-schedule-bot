"""Links for lesson cards: rooms -> building on the map, teachers -> schedule on tulsu.ru.

Only links that can be justified are produced:

* a room gets a link when the building prefix of its name (``Гл.`` in ``Гл.-402``, ``9`` in
  ``9-324``) is listed in ``data/tulgu_buildings.toml``;
* a teacher gets a link to the university's schedule search
  (``https://tulsu.ru/schedule/?search=<full name>``) - the same page the official schedule
  links teachers to - but only for names that came from the university's own data.

Everything else yields ``None`` and is rendered as plain text.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from urllib.parse import quote

TEACHER_SEARCH_URL = "https://tulsu.ru/schedule/?search={query}"
BUILDINGS_FILE = "tulgu_buildings.toml"


@dataclass(frozen=True, slots=True)
class Building:
    prefixes: tuple[str, ...]
    name: str
    address: str
    page: str


@dataclass(frozen=True, slots=True)
class BuildingMap:
    map_url: str
    buildings: tuple[Building, ...]

    def find(self, room: str) -> Building | None:
        """The building of ``room`` (``Гл.-402`` -> Главный корпус) or ``None`` if unknown."""
        prefix, sep, rest = room.strip().partition("-")
        prefix = prefix.strip().casefold()
        if not sep or not rest.strip() or not prefix:
            return None
        for building in self.buildings:
            if prefix in (p.casefold() for p in building.prefixes):
                return building
        return None

    def room_url(self, room: str) -> str | None:
        building = self.find(room)
        if building is None or not building.address:
            return None
        return self.map_url.replace("{query}", quote(building.address, safe=""))


def parse_buildings(data: dict) -> BuildingMap:
    """Build a :class:`BuildingMap` from parsed TOML; raises ``ValueError`` on bad entries."""
    map_url = data.get("map_url", "")
    if not map_url.startswith("https://") or "{query}" not in map_url:
        raise ValueError("map_url must be an https URL containing {query}")
    buildings = []
    seen: set[str] = set()
    for entry in data.get("building", []):
        prefixes = tuple(entry.get("prefixes", ()))
        if not prefixes or not all(isinstance(p, str) and p.strip() for p in prefixes):
            raise ValueError(f"building without prefixes: {entry!r}")
        for prefix in prefixes:
            key = prefix.strip().casefold()
            if key in seen or "-" in key:
                raise ValueError(f"duplicate or invalid prefix: {prefix!r}")
            seen.add(key)
        buildings.append(
            Building(
                prefixes=prefixes,
                name=entry.get("name", ""),
                address=entry.get("address", "").strip(),
                page=entry.get("page", ""),
            )
        )
    return BuildingMap(map_url=map_url, buildings=tuple(buildings))


@lru_cache(maxsize=1)
def load_building_map() -> BuildingMap:
    text = (resources.files("schedule_bot") / "data" / BUILDINGS_FILE).read_text("utf-8")
    return parse_buildings(tomllib.loads(text))


def room_url(room: str) -> str | None:
    """Map link for a room, or ``None`` when the building is unknown."""
    return load_building_map().room_url(room)


def teacher_url(name: str) -> str | None:
    """Link to the teacher's schedule on tulsu.ru for a full name, or ``None`` for empty input."""
    name = " ".join(name.split())
    if not name:
        return None
    return TEACHER_SEARCH_URL.replace("{query}", quote(name, safe=""))
