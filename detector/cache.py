"""Local JSON cache for OSM lookups.

Keyed by coordinates rounded to 5 decimal places (~1 m precision).
Cache file lives at .osm_cache.json in the working directory (gitignored).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

CACHE_FILE = ".osm_cache.json"


def _load() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                return {}
    return {}


def _save(data: dict) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _key(lat: float, lng: float) -> str:
    return f"{round(lat, 5)},{round(lng, 5)}"


def get(lat: float, lng: float) -> Optional[dict]:
    return _load().get(_key(lat, lng))


def set(lat: float, lng: float, value: dict) -> None:  # noqa: A001
    data = _load()
    data[_key(lat, lng)] = value
    _save(data)


def clear_cache() -> None:
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print(f"[cache] cleared {CACHE_FILE}")
    else:
        print(f"[cache] nothing to clear ({CACHE_FILE} does not exist)")
