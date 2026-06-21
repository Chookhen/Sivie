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


def generate_mock_track(
    num_points: int = 120,
    start_lat: float = 37.8716,
    start_lng: float = -122.2727,
    spacing_sec: float = 1.0,
) -> list[TrackPoint]:
    points: list[TrackPoint] = []
    lat, lng = start_lat, start_lng
    for i in range(num_points):
        points.append(TrackPoint(time_offset_sec=i * spacing_sec, lat=lat, lng=lng))
        lat += 0.0003
        lng += 0.0001
    return points
