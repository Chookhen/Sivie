"""Persistent hazard database + street-level aggregation.

This is the "connected data" layer. Every run merges its detections into a
persistent JSON database keyed by physical location:

- A detection is matched against existing hazards of the SAME type within
  ``match_radius_m``. A match means we've seen this exact hazard before
  (times_seen += 1), NOT a new one.
- A genuinely new hazard is appended with a stable ``hazard_id``.

From the accumulated database we roll up per-street statistics (how many
potholes / cracks on each street) and derive a ``street_weight`` that grows
with hazard density. Both the per-hazard history and the street weight are
attached back onto each detection so the scorer, Gemini, and the UI can all
use them.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any

DEFAULT_DB_PATH = os.getenv("HAZARD_DB_PATH", "hazard_db.json")
UNKNOWN_STREET = "Unknown road"

# When OSM road names are unavailable (e.g. synthetic GPS), hazards are grouped
# into ~110 m spatial buckets and given a stable, readable street label drawn
# from this list. The bucket->name mapping is persisted so it stays consistent
# across runs.
BERKELEY_STREETS = [
    "Shattuck Ave", "University Ave", "Telegraph Ave", "Bancroft Way",
    "Dwight Way", "Ashby Ave", "College Ave", "Martin Luther King Jr Way",
    "Sacramento St", "San Pablo Ave", "Hearst Ave", "Addison St",
    "Channing Way", "Durant Ave", "Allston Way", "Center St",
    "Oxford St", "Milvia St", "Adeline St", "Gilman St",
    "Solano Ave", "Cedar St", "Russell St", "Alcatraz Ave",
]


def _bucket(lat: float, lng: float, precision: int = 3) -> str:
    return f"{round(lat, precision)},{round(lng, precision)}"


def _resolve_street_name(det: dict, db: dict) -> str:
    """Return a stable street label, falling back to a spatial-bucket name."""
    name = det.get("road_name")
    if name and name != UNKNOWN_STREET:
        return name
    lat, lng = det.get("lat"), det.get("lng")
    if lat is None or lng is None:
        return UNKNOWN_STREET
    mapping: dict[str, str] = db.setdefault("street_names", {})
    key = _bucket(lat, lng)
    if key not in mapping:
        idx = db.get("name_cursor", 0)
        base = BERKELEY_STREETS[idx % len(BERKELEY_STREETS)]
        cycle = idx // len(BERKELEY_STREETS)
        mapping[key] = base if cycle == 0 else f"{base} ({cycle + 1})"
        db["name_cursor"] = idx + 1
    return mapping[key]


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _street_weight(total: int) -> float:
    """Street weight grows with hazard count, capped so it stays bounded.

    1 hazard -> 1.0, then +0.2 each, capped at 3.0. A street that keeps
    accumulating defects becomes systematically more urgent.
    """
    return round(min(3.0, 1.0 + 0.2 * max(0, total - 1)), 2)


def _load_db(path: str) -> dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            data.setdefault("hazards", [])
            data.setdefault("next_id", len(data["hazards"]) + 1)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"hazards": [], "next_id": 1}


def _save_db(path: str, db: dict[str, Any]) -> None:
    db["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(db, fh, indent=2)


def update_and_aggregate(
    report_dict: dict,
    db_path: str = DEFAULT_DB_PATH,
    match_radius_m: float = 20.0,
    persist: bool = True,
) -> dict[str, Any]:
    """Merge detections into the persistent DB and attach street stats.

    Returns a street rollup: {street_name: {potholes, cracks, total, weight}}.
    """
    db = _load_db(db_path)
    hazards: list[dict[str, Any]] = db["hazards"]
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0

    for det in report_dict.get("detections", []):
        lat, lng = det.get("lat"), det.get("lng")
        dtype = det["type"]
        if lat is None or lng is None:
            continue

        # Resolve a stable street label (OSM name, or spatial-bucket fallback).
        det["road_name"] = _resolve_street_name(det, db)

        match = None
        for h in hazards:
            if h["type"] != dtype:
                continue
            if _haversine_m(lat, lng, h["lat"], h["lng"]) <= match_radius_m:
                match = h
                break

        if match is not None:
            match["times_seen"] = match.get("times_seen", 1) + 1
            match["last_seen"] = now
            if not match.get("road_name") and det.get("road_name"):
                match["road_name"] = det.get("road_name")
            det["hazard_id"] = match["hazard_id"]
            det["times_seen"] = match["times_seen"]
        else:
            hazard_id = f"H{db['next_id']:05d}"
            db["next_id"] += 1
            new_count += 1
            hazards.append({
                "hazard_id": hazard_id,
                "type": dtype,
                "lat": lat,
                "lng": lng,
                "road_name": det.get("road_name") or UNKNOWN_STREET,
                "first_seen": now,
                "last_seen": now,
                "times_seen": 1,
            })
            det["hazard_id"] = hazard_id
            det["times_seen"] = 1

    # Roll up per-street stats from the FULL database (not just this run).
    streets: dict[str, dict[str, Any]] = {}
    for h in hazards:
        name = h.get("road_name") or UNKNOWN_STREET
        s = streets.setdefault(name, {"potholes": 0, "cracks": 0, "total": 0})
        if h["type"] == "pothole":
            s["potholes"] += 1
        elif h["type"] == "crack":
            s["cracks"] += 1
        s["total"] += 1
    for name, s in streets.items():
        s["weight"] = _street_weight(s["total"])

    # Attach street stats back onto each detection.
    for det in report_dict.get("detections", []):
        name = det.get("road_name") or UNKNOWN_STREET
        s = streets.get(name)
        if s is None:
            continue
        det["street_hazard_count"] = s["total"]
        det["street_pothole_count"] = s["potholes"]
        det["street_crack_count"] = s["cracks"]
        det["street_weight"] = s["weight"]

    if persist:
        _save_db(db_path, db)

    print(
        f"[street] DB now holds {len(hazards)} unique hazards across "
        f"{len(streets)} street(s); +{new_count} new this run"
    )
    return streets
