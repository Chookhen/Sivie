"""OSM reverse-geocode and nearby-POI enrichment.

Uses Nominatim for road name/class and Overpass for POIs within a radius.
Enriched fields are attached directly to detection dicts (post-Pydantic dump).
"""

from __future__ import annotations

import math
import time
from typing import Any

import requests

from . import cache as _cache
from .schema import RawIssue, RoadContext
from .scoring import compute_priority, priority_label

USER_AGENT = "road-hazard-detector/1.0 (github.com/road-hazard-detector)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_ROAD_CLASS_TO_CONTEXT: dict[str, RoadContext] = {
    "motorway": RoadContext.FREEWAY,
    "motorway_link": RoadContext.FREEWAY,
    "trunk": RoadContext.FREEWAY,
    "trunk_link": RoadContext.FREEWAY,
    "primary": RoadContext.ARTERIAL,
    "primary_link": RoadContext.ARTERIAL,
    "secondary": RoadContext.ARTERIAL,
    "secondary_link": RoadContext.ARTERIAL,
    "tertiary": RoadContext.ARTERIAL,
    "tertiary_link": RoadContext.ARTERIAL,
    "residential": RoadContext.RESIDENTIAL,
    "living_street": RoadContext.RESIDENTIAL,
    "service": RoadContext.RESIDENTIAL,
    "unclassified": RoadContext.RESIDENTIAL,
}

_last_nominatim: float = 0.0
_last_overpass: float = 0.0


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _throttle_nominatim() -> None:
    global _last_nominatim
    elapsed = time.monotonic() - _last_nominatim
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_nominatim = time.monotonic()


def _throttle_overpass() -> None:
    global _last_overpass
    elapsed = time.monotonic() - _last_overpass
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_overpass = time.monotonic()


def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    """Return {road_name, road_class} from Nominatim. Failure -> Nones."""
    _throttle_nominatim()
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 17},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        road_name = (
            data.get("address", {}).get("road")
            or data.get("address", {}).get("footway")
            or data.get("name")
        )
        road_class: str | None = None
        if data.get("category") == "highway":
            road_class = data.get("type")
        return {"road_name": road_name, "road_class": road_class}
    except Exception:  # noqa: BLE001
        return {"road_name": None, "road_class": None}


def nearby_pois(lat: float, lng: float, radius_m: int = 50) -> list[dict[str, Any]]:
    """Return POIs within radius_m of (lat, lng) from Overpass.

    Genuine empty result -> []. Persistent failure -> [] with a logged warning.
    """
    _throttle_overpass()
    query = (
        f"[out:json][timeout:15];\n"
        f"(\n"
        f'  node["amenity"="school"](around:{radius_m},{lat},{lng});\n'
        f'  node["amenity"="hospital"](around:{radius_m},{lat},{lng});\n'
        f'  node["amenity"="kindergarten"](around:{radius_m},{lat},{lng});\n'
        f'  node["highway"="crossing"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="school"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="hospital"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="kindergarten"](around:{radius_m},{lat},{lng});\n'
        f");\n"
        f"out center;"
    )
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5 * attempt))
                if attempt < 3:
                    print(f"[osm] overpass rate-limited, waiting {wait}s (retry {attempt}/3)\u2026")
                    time.sleep(wait)
                    continue
                break
            resp.raise_for_status()
            pois: list[dict[str, Any]] = []
            for el in resp.json().get("elements", []):
                tags = el.get("tags", {})
                el_lat = el.get("lat") or el.get("center", {}).get("lat")
                el_lng = el.get("lon") or el.get("center", {}).get("lon")
                if el_lat is None or el_lng is None:
                    continue
                category = tags.get("amenity") or tags.get("highway") or "unknown"
                pois.append({
                    "name": tags.get("name"),
                    "category": category,
                    "distance_m": round(_haversine(lat, lng, el_lat, el_lng), 1),
                })
            return sorted(pois, key=lambda p: p["distance_m"])
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as exc:
            wait = 5 * attempt
            if attempt < 3:
                print(f"[osm] overpass error ({type(exc).__name__}), waiting {wait}s (retry {attempt}/3)\u2026")
                time.sleep(wait)
        except Exception as exc:  # noqa: BLE001 - non-retriable (e.g. bad JSON)
            print(f"[osm] WARN overpass failed for {lat},{lng}; POIs unknown ({exc})")
            return []
    print(f"[osm] WARN overpass failed for {lat},{lng}; POIs unknown")
    return []


def enrich(report_dict: dict, use_cache: bool = True) -> dict:
    """Attach road_name, road_class, nearby_pois to each detection in-place.

    Also overwrites road_context with OSM ground-truth and recomputes priority.
    """
    detections = report_dict.get("detections", [])
    total = sum(1 for d in detections if d.get("lat") is not None)
    done = 0

    for det in detections:
        lat = det.get("lat")
        lng = det.get("lng")
        if lat is None or lng is None:
            continue

        cached = _cache.get(lat, lng) if use_cache else None
        if cached is not None:
            geo = cached["geocode"]
            pois = cached["pois"]
        else:
            geo = reverse_geocode(lat, lng)
            pois = nearby_pois(lat, lng)
            if use_cache:
                _cache.set(lat, lng, {"geocode": geo, "pois": pois})

        det["road_name"] = geo.get("road_name")
        det["road_class"] = geo.get("road_class")
        det["nearby_pois"] = pois

        road_class = det.get("road_class")
        if road_class:
            new_context = _ROAD_CLASS_TO_CONTEXT.get(road_class)
            if new_context is not None:
                det["road_context_vision"] = det.get("road_context")
                det["road_context"] = new_context.value
                issue = RawIssue(
                    type=det["type"],
                    description=det.get("description", ""),
                    severity=det["severity"],
                    confidence=det["confidence"],
                    road_context=new_context,
                )
                new_priority = compute_priority(issue)
                det["priority"] = new_priority
                det["priority_label"] = priority_label(new_priority).value

        done += 1
        print(f"[osm] enriched {done}/{total} | {det.get('road_name') or 'unknown road'}")

    report_dict["detections"].sort(key=lambda d: d["priority"], reverse=True)
    return report_dict
