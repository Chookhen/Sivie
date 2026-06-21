from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class TrackPoint:
    time_offset_sec: float
    lat: float
    lng: float


def load_track(path: str) -> list[TrackPoint]:
    if path.endswith(".gpx"):
        import gpxpy  # type: ignore[import]

        with open(path, encoding="utf-8") as fh:
            gpx = gpxpy.parse(fh)
        raw: list[tuple[datetime, float, float]] = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    raw.append((point.time, point.latitude, point.longitude))
        if not raw:
            return []
        raw.sort(key=lambda x: x[0])
        origin = raw[0][0]
        return [
            TrackPoint(
                time_offset_sec=(t - origin).total_seconds(),
                lat=lat,
                lng=lng,
            )
            for t, lat, lng in raw
        ]
    raw_csv: list[tuple[float, float, float]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts_raw = row["timestamp"].strip()
            try:
                ts = float(ts_raw)
            except ValueError:
                dt = datetime.fromisoformat(ts_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
            raw_csv.append((ts, float(row["lat"]), float(row["lng"])))
    if not raw_csv:
        return []
    raw_csv.sort(key=lambda x: x[0])
    origin_ts = raw_csv[0][0]
    return [
        TrackPoint(time_offset_sec=ts - origin_ts, lat=lat, lng=lng)
        for ts, lat, lng in raw_csv
    ]


def interpolate(track: list[TrackPoint], t: float) -> tuple[float, float]:
    if not track:
        raise ValueError("track is empty")
    if t <= track[0].time_offset_sec:
        return track[0].lat, track[0].lng
    if t >= track[-1].time_offset_sec:
        return track[-1].lat, track[-1].lng
    lo, hi = 0, len(track) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if track[mid].time_offset_sec <= t:
            lo = mid
        else:
            hi = mid
    a, b = track[lo], track[hi]
    frac = (t - a.time_offset_sec) / (b.time_offset_sec - a.time_offset_sec)
    return a.lat + frac * (b.lat - a.lat), a.lng + frac * (b.lng - a.lng)


def apply_gps(
    report_dict: dict,
    track: list[TrackPoint],
    time_offset: float = 0.0,
) -> dict:
    for det in report_dict.get("detections", []):
        t = det["timestamp_offset_sec"] + time_offset
        lat, lng = interpolate(track, t)
        det["lat"] = lat
        det["lng"] = lng
    return report_dict


def _parse_dt(val: str) -> "datetime | None":
    """Parse an ISO-8601 timestamp into an aware UTC-comparable datetime."""
    val = (val or "").strip()
    if not val:
        return None
    if val.endswith("Z"):
        val = val[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(val)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_video_start_time(path: str) -> "datetime | None":
    """Best-effort absolute start time of a video from its container metadata.

    iPhone .mov files carry a UTC ``creation_time`` (and a local-tz
    ``com.apple.quicktime.creationdate``); either resolves to the same instant.
    Returns None for image folders or files without timestamps.
    """
    try:
        import ffmpeg  # type: ignore[import]

        meta = ffmpeg.probe(path)
    except Exception:
        return None
    fmt_tags = (meta.get("format", {}) or {}).get("tags", {}) or {}
    for key in ("creation_time", "com.apple.quicktime.creationdate"):
        dt = _parse_dt(fmt_tags.get(key, ""))
        if dt:
            return dt
    for stream in meta.get("streams", []) or []:
        dt = _parse_dt((stream.get("tags") or {}).get("creation_time", ""))
        if dt:
            return dt
    return None


def get_track_origin_time(path: str) -> "datetime | None":
    """Absolute timestamp of the first point in a GPX/CSV track, if present."""
    if path.endswith(".gpx"):
        import gpxpy  # type: ignore[import]

        with open(path, encoding="utf-8") as fh:
            gpx = gpxpy.parse(fh)
        times = [
            p.time
            for track in gpx.tracks
            for seg in track.segments
            for p in seg.points
            if p.time is not None
        ]
        return min(times) if times else None
    times_csv: list[datetime] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts_raw = row["timestamp"].strip()
            try:
                times_csv.append(datetime.fromtimestamp(float(ts_raw), tz=timezone.utc))
            except ValueError:
                dt = _parse_dt(ts_raw)
                if dt:
                    times_csv.append(dt)
    return min(times_csv) if times_csv else None


def auto_time_offset(video_path: str, track_path: str) -> "float | None":
    """Seconds to add to a video-relative time to land on the track timeline.

    offset = (video_start - track_origin); feed it as ``time_offset`` to
    ``apply_gps``. Returns None when either timestamp is unavailable.
    """
    vstart = get_video_start_time(video_path)
    torigin = get_track_origin_time(track_path)
    if vstart is None or torigin is None:
        return None
    return (vstart - torigin).total_seconds()


def generate_mock_track(
    duration_sec: float = 120.0,
    start_lat: float = 37.8716,
    start_lng: float = -122.2727,
    spacing_sec: float = 1.0,
) -> list[TrackPoint]:
    """Synthetic dashcam route around Berkeley, covering the full duration.

    Produces a gently wandering path (slow heading changes) so detections
    spread across a neighborhood instead of piling on a single point or
    drifting off in a straight line. Deterministic.
    """
    import math

    n = max(2, int(duration_sec / spacing_sec) + 1)
    points: list[TrackPoint] = []
    lat, lng = start_lat, start_lng
    heading = 0.0
    step = 0.00010  # ~11 m per step ≈ 40 km/h at 1 s spacing
    for i in range(n):
        points.append(TrackPoint(time_offset_sec=i * spacing_sec, lat=lat, lng=lng))
        heading += math.sin(i * 0.04) * 0.25  # gentle turns
        lat += step * math.cos(heading)
        lng += step * math.sin(heading) / math.cos(math.radians(lat))
    return points
