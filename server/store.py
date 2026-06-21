"""Storage backends for the operations database.

Two interchangeable stores share one interface:

- ``JsonStore``      persists to a local JSON file (zero setup).
- ``SupabaseStore``  persists to a hosted Supabase Postgres table via PostgREST.

``get_store()`` returns the Supabase store when ``SUPABASE_URL`` and a key are
configured, otherwise it falls back to the JSON store. The FastAPI layer is
identical for both, so migrating is purely an environment-variable change.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import List, Optional, Tuple

import requests
from dotenv import load_dotenv

from .models import Occurrence, OccurrenceCreate, OccurrenceUpdate, clamp_score

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETECTIONS_PATH = os.getenv(
    "DETECTIONS_PATH", os.path.join(ROOT, "web", "public", "detections.json")
)
DB_PATH = os.getenv("OCCURRENCE_DB_PATH", os.path.join(ROOT, "data", "occurrences.json"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "occurrences")


# --------------------------------------------------------------------------- #
# Seeding from the detection output
# --------------------------------------------------------------------------- #
def build_occurrences_from_detections() -> Tuple[List[Occurrence], Optional[str]]:
    """Construct occurrences from the latest detection output.

    Locations are only kept when the pipeline recorded a real GPX source;
    synthetic/no-GPS footage is seeded with null coordinates (no map markers).
    """
    if not os.path.exists(DETECTIONS_PATH):
        return [], None
    with open(DETECTIONS_PATH, encoding="utf-8") as fh:
        report = json.load(fh)

    location_available = report.get("gps_source") == "gpx"
    occurrences: List[Occurrence] = []
    for d in report.get("detections", []):
        score = d.get("final_priority")
        if score is None:
            score = d.get("priority", 0.0)
        occurrences.append(Occurrence(
            id=d.get("hazard_id") or f"H{uuid.uuid4().hex[:8]}",
            type=d.get("type", "other"),
            description=d.get("description", ""),
            severity=int(d.get("severity", 3) or 3),
            score=clamp_score(float(score or 0.0)),
            confidence=d.get("confidence"),
            road_name=d.get("road_name") if location_available else None,
            road_context=d.get("road_context"),
            frame=d.get("frame"),
            image_url=d.get("image_url"),
            lat=d.get("lat") if location_available else None,
            lng=d.get("lng") if location_available else None,
            justification=d.get("justification") or [],
            priority_multiplier=d.get("priority_multiplier"),
            times_seen=int(d.get("times_seen", 1) or 1),
            source="detection",
        ))

    # Collapse repeat detections of the same physical hazard to one row
    # (the primary key is the hazard id). Keep the highest-scoring instance.
    by_id: dict = {}
    for o in occurrences:
        existing = by_id.get(o.id)
        if existing is None or o.score > existing.score:
            by_id[o.id] = o
    deduped = sorted(by_id.values(), key=lambda o: o.score, reverse=True)
    return deduped, report.get("source")


def _occurrence_from_create(payload: OccurrenceCreate) -> Occurrence:
    score = payload.score
    if score is None:
        score = payload.severity * 2.0  # map 1-5 severity onto the 0-10 scale
    return Occurrence(
        id=f"M{uuid.uuid4().hex[:8]}",
        type=payload.type,
        description=payload.description,
        severity=payload.severity,
        score=clamp_score(float(score)),
        road_name=payload.road_name,
        road_context=payload.road_context,
        lat=payload.lat,
        lng=payload.lng,
        source="manual",
    )


# --------------------------------------------------------------------------- #
# JSON file store
# --------------------------------------------------------------------------- #
class JsonStore:
    backend = "json"

    def __init__(self) -> None:
        self._source_video: Optional[str] = None

    def _read(self) -> dict:
        if os.path.exists(DB_PATH):
            with open(DB_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        occ, source = build_occurrences_from_detections()
        data = {"source_video": source, "occurrences": [o.model_dump() for o in occ]}
        self._write(data)
        return data

    def _write(self, data: dict) -> None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with open(DB_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def list(self) -> Tuple[List[Occurrence], Optional[str]]:
        data = self._read()
        return [Occurrence(**o) for o in data.get("occurrences", [])], data.get("source_video")

    def create(self, payload: OccurrenceCreate) -> Occurrence:
        data = self._read()
        occ = _occurrence_from_create(payload)
        data.setdefault("occurrences", []).append(occ.model_dump())
        self._write(data)
        return occ

    def update(self, occ_id: str, payload: OccurrenceUpdate) -> Occurrence:
        data = self._read()
        for row in data.get("occurrences", []):
            if row["id"] == occ_id:
                patch = payload.model_dump(exclude_unset=True)
                if patch.get("score") is not None:
                    patch["score"] = clamp_score(float(patch["score"]))
                row.update(patch)
                self._write(data)
                return Occurrence(**row)
        raise KeyError(occ_id)

    def delete(self, occ_id: str) -> bool:
        data = self._read()
        rows = data.get("occurrences", [])
        new_rows = [o for o in rows if o["id"] != occ_id]
        if len(new_rows) == len(rows):
            return False
        data["occurrences"] = new_rows
        self._write(data)
        return True

    def reseed(self) -> int:
        occ, source = build_occurrences_from_detections()
        self._write({"source_video": source, "occurrences": [o.model_dump() for o in occ]})
        return len(occ)


# --------------------------------------------------------------------------- #
# Supabase (PostgREST) store
# --------------------------------------------------------------------------- #
class SupabaseStore:
    backend = "supabase"

    def __init__(self) -> None:
        self.base = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }

    def _check(self, res: requests.Response) -> None:
        if not res.ok:
            raise RuntimeError(f"Supabase error {res.status_code}: {res.text}")

    def list(self) -> Tuple[List[Occurrence], Optional[str]]:
        res = requests.get(
            self.base, headers=self.headers,
            params={"select": "*", "order": "score.desc"}, timeout=15,
        )
        self._check(res)
        occ = [Occurrence(**row) for row in res.json()]
        # source_video isn't stored per-row; surface it from the detection file.
        _, source = build_occurrences_from_detections()
        return occ, source

    def create(self, payload: OccurrenceCreate) -> Occurrence:
        occ = _occurrence_from_create(payload)
        res = requests.post(
            self.base, headers={**self.headers, "Prefer": "return=representation"},
            json=occ.model_dump(), timeout=15,
        )
        self._check(res)
        return Occurrence(**res.json()[0])

    def update(self, occ_id: str, payload: OccurrenceUpdate) -> Occurrence:
        patch = payload.model_dump(exclude_unset=True)
        if patch.get("score") is not None:
            patch["score"] = clamp_score(float(patch["score"]))
        res = requests.patch(
            self.base, headers={**self.headers, "Prefer": "return=representation"},
            params={"id": f"eq.{occ_id}"}, json=patch, timeout=15,
        )
        self._check(res)
        rows = res.json()
        if not rows:
            raise KeyError(occ_id)
        return Occurrence(**rows[0])

    def delete(self, occ_id: str) -> bool:
        res = requests.delete(
            self.base, headers={**self.headers, "Prefer": "return=representation"},
            params={"id": f"eq.{occ_id}"}, timeout=15,
        )
        self._check(res)
        return bool(res.json())

    def reseed(self) -> int:
        # Clear the table, then bulk-insert from the detection output.
        wipe = requests.delete(self.base, headers=self.headers,
                               params={"id": "not.is.null"}, timeout=30)
        self._check(wipe)
        occ, _ = build_occurrences_from_detections()
        if occ:
            res = requests.post(
                self.base,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                params={"on_conflict": "id"},
                json=[o.model_dump() for o in occ], timeout=30,
            )
            self._check(res)
        return len(occ)


def get_store():
    if SUPABASE_URL and SUPABASE_KEY:
        return SupabaseStore()
    return JsonStore()
