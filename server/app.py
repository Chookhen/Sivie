"""Government operations backend for the road-hazard database.

A small FastAPI service exposing the hazard occurrence database (review, add,
remove). Storage is pluggable (see ``server/store.py``): it uses Supabase
Postgres when ``SUPABASE_URL`` + key are configured, and otherwise falls back to
a local JSON file. The API contract is identical for both backends.

Run it with:
    uvicorn server.app:app --reload --port 8000

- Each occurrence stores an EXACT location (lat/lng) when available.
- Footage without real GPS is seeded with null coordinates, so the map shows no
  markers for it (``located_count`` will be 0).
- Map colour is driven by a 0-10 ``score`` (white 0-4, orange 4-7, red 7-10).
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .jobs import active_job, get_job, start_job
from .models import Occurrence, OccurrenceCreate, OccurrenceUpdate
from .store import get_store

app = FastAPI(title="Road Hazard Operations DB", version="1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "backend": get_store().backend}


@app.get("/api/occurrences")
def list_occurrences() -> dict:
    store = get_store()
    occurrences, source_video = store.list()
    located = sum(1 for o in occurrences if o.lat is not None and o.lng is not None)
    return {
        "backend": store.backend,
        "location_available": located > 0,
        "source_video": source_video,
        "count": len(occurrences),
        "located_count": located,
        "occurrences": [o.model_dump() for o in occurrences],
    }


@app.post("/api/occurrences", status_code=201)
def create_occurrence(payload: OccurrenceCreate) -> Occurrence:
    return get_store().create(payload)


@app.patch("/api/occurrences/{occ_id}")
def update_occurrence(occ_id: str, payload: OccurrenceUpdate) -> Occurrence:
    try:
        return get_store().update(occ_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Occurrence {occ_id} not found")


@app.delete("/api/occurrences/{occ_id}")
def delete_occurrence(occ_id: str) -> dict:
    if not get_store().delete(occ_id):
        raise HTTPException(status_code=404, detail=f"Occurrence {occ_id} not found")
    return {"deleted": occ_id}


@app.post("/api/reseed")
def reseed() -> dict:
    return {"reseeded": True, "count": get_store().reseed()}


# --------------------------------------------------------------------------- #
# Processing: list / upload source files and run the detection pipeline
# --------------------------------------------------------------------------- #
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(ROOT, "data", "uploads")
DATA_DIRS = [
    os.path.join(ROOT, "test_images"),
    os.path.join(ROOT, "samples"),
    UPLOAD_DIR,
]
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
GPS_EXTS = {".gpx", ".csv"}
DETECTIONS_OUT = os.path.join(ROOT, "web", "public", "detections.json")
FRAMES_OUT = os.path.join(ROOT, "web", "public", "frames")
BACKUP_DIR = os.path.join(ROOT, "data", "backups")
MAX_BACKUPS = 10


def _backup_detections() -> Optional[str]:
    """Snapshot the current detections.json before a run overwrites it.

    A processing run replaces detections.json and wipes frames/, so without this
    a run would silently destroy the previous (possibly hand-curated) dataset.
    Keeps the most recent MAX_BACKUPS snapshots.
    """
    if not os.path.isfile(DETECTIONS_OUT):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    import time as _time
    stamp = _time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"detections_{stamp}.json")
    shutil.copy2(DETECTIONS_OUT, dest)
    backups = sorted(
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("detections_") and f.endswith(".json")
    )
    for stale in backups[:-MAX_BACKUPS]:
        try:
            os.remove(os.path.join(BACKUP_DIR, stale))
        except OSError:
            pass
    return dest


def _resolve_in_data(rel_path: str) -> str:
    """Resolve a client-supplied path and confirm it stays inside an allowed dir."""
    candidate = os.path.realpath(os.path.join(ROOT, rel_path))
    for d in DATA_DIRS:
        base = os.path.realpath(d)
        if candidate == base or candidate.startswith(base + os.sep):
            if os.path.isfile(candidate):
                return candidate
            break
    raise HTTPException(status_code=400, detail=f"File not allowed or missing: {rel_path}")


def _describe(path: str, base_dir: str, kind: str) -> dict:
    return {
        "name": os.path.basename(path),
        "path": os.path.relpath(path, ROOT),
        "dir": os.path.relpath(base_dir, ROOT),
        "size": os.path.getsize(path),
        "modified": os.path.getmtime(path),
        "kind": kind,
    }


@app.get("/api/files")
def list_files() -> dict:
    videos, gps = [], []
    for d in DATA_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in VIDEO_EXTS:
                videos.append(_describe(p, d, "video"))
            elif ext in GPS_EXTS:
                gps.append(_describe(p, d, "gps"))
    return {
        "videos": videos,
        "gps": gps,
        "upload_dir": os.path.relpath(UPLOAD_DIR, ROOT),
    }


@app.post("/api/upload")
async def upload(request: Request, filename: str = Query(...), kind: str = Query("video")) -> dict:
    safe = os.path.basename(filename)
    if not safe:
        raise HTTPException(status_code=400, detail="Missing filename")
    ext = os.path.splitext(safe)[1].lower()
    allowed = VIDEO_EXTS if kind == "video" else GPS_EXTS
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported {kind} extension: {ext}")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest = os.path.join(UPLOAD_DIR, safe)
    size = 0
    with open(dest, "wb") as fh:
        async for chunk in request.stream():
            fh.write(chunk)
            size += len(chunk)
    return _describe(dest, UPLOAD_DIR, kind)


class ProcessRequest(BaseModel):
    video: str
    gps: Optional[str] = None
    time_offset: float = -3.0
    no_auto_sync: bool = False
    fps: float = 1.0
    max_frames: Optional[int] = None
    detector: str = "yolo"
    yolo_conf: float = 0.25
    min_confidence: float = 0.0
    mock: bool = False
    mock_gps: bool = False
    dedupe: bool = True
    enrich: bool = True
    ai_priority: bool = False
    ai_mock: bool = False


@app.post("/api/process")
def start_process(req: ProcessRequest) -> dict:
    if active_job() is not None:
        raise HTTPException(status_code=409, detail="A processing job is already running.")

    video_abs = _resolve_in_data(req.video)

    # Snapshot the existing dataset before we overwrite it (prevents data loss).
    backup = _backup_detections()

    # Start from a clean frame dir so the gallery only shows this run's frames.
    shutil.rmtree(FRAMES_OUT, ignore_errors=True)
    os.makedirs(FRAMES_OUT, exist_ok=True)

    cmd = [
        sys.executable, "main.py",
        "--input", video_abs,
        "--output", DETECTIONS_OUT,
        "--save-frames-dir", FRAMES_OUT,
        "--fps", str(req.fps),
        "--detector", req.detector,
        "--yolo-conf", str(req.yolo_conf),
        "--min-confidence", str(req.min_confidence),
        "--time-offset", str(req.time_offset),
    ]
    if req.gps:
        cmd += ["--gpx", _resolve_in_data(req.gps)]
    elif req.mock_gps:
        cmd += ["--mock-gps"]
    if req.no_auto_sync:
        cmd += ["--no-auto-sync"]
    if req.max_frames:
        cmd += ["--max-frames", str(req.max_frames)]
    if req.mock:
        cmd += ["--mock"]
    if req.dedupe:
        cmd += ["--dedupe"]
    if req.enrich:
        cmd += ["--enrich"]
    if req.ai_priority:
        cmd += ["--ai-priority"]
        if req.ai_mock:
            cmd += ["--ai-mock"]

    def on_success() -> Optional[str]:
        try:
            n = get_store().reseed()
            return f"[post] reseeded operations DB from detections: {n} occurrence(s)"
        except Exception as exc:  # noqa: BLE001
            return f"[post] reseed skipped: {exc}"

    job = start_job(cmd, label=os.path.basename(video_abs), on_success=on_success)
    if backup:
        job.append(f"[backup] previous dataset saved -> {os.path.relpath(backup, ROOT)}")
    return {"job_id": job.id, "backup": (os.path.relpath(backup, ROOT) if backup else None), **job.snapshot()}


@app.get("/api/process")
def current_process() -> dict:
    job = active_job()
    return {"active": job.id if job else None}


@app.get("/api/process/{job_id}")
def process_status(job_id: str, offset: int = 0) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.snapshot(since=offset)
