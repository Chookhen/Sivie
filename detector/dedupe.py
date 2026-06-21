"""Post-detection deduplication + best-frame selection.

Groups temporally (and spatially) adjacent detections of the same type into
clusters, then keeps only the sharpest/largest-box representative per cluster.
"""

from __future__ import annotations

import math
import os
from typing import Any

from .frame_extraction import laplacian_variance


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _boxes_match(b1: list[int], b2: list[int]) -> bool:
    """True if boxes overlap (IoU > 0) or their centres are within 250 units."""
    y1min, x1min, y1max, x1max = b1
    y2min, x2min, y2max, x2max = b2
    if min(y1max, y2max) > max(y1min, y2min) and min(x1max, x2max) > max(x1min, x2min):
        return True
    cy1, cx1 = (y1min + y1max) / 2, (x1min + x1max) / 2
    cy2, cx2 = (y2min + y2max) / 2, (x2min + x2max) / 2
    return math.sqrt((cy1 - cy2) ** 2 + (cx1 - cx2) ** 2) < 250.0


def _box_area(d: dict) -> int:
    b = d.get("box_2d")
    if not b:
        return 0
    ymin, xmin, ymax, xmax = b
    return (ymax - ymin) * (xmax - xmin)


def _pick_best(cluster: list[dict], frames_dir: str | None, sharpness_floor: float) -> dict:
    if frames_dir:
        scored = [(d, laplacian_variance(os.path.join(frames_dir, d["frame"]))) for d in cluster]
        sharp = [(d, s) for d, s in scored if s is not None and s >= sharpness_floor]
        if sharp:
            return max(sharp, key=lambda x: _box_area(x[0]))[0]

    if any(d.get("box_2d") for d in cluster):
        return max(cluster, key=_box_area)

    return max(cluster, key=lambda d: d["confidence"])


def dedupe(
    report_dict: dict,
    use_gps: bool = False,
    frames_dir: str | None = None,
    time_gap_s: float = 2.0,
    gps_radius_m: float = 18.0,
    sharpness_floor: float = 80.0,
) -> dict:
    """Collapse duplicate detections of the same physical hazard in-place."""
    detections: list[dict] = sorted(
        report_dict.get("detections", []),
        key=lambda d: d["timestamp_offset_sec"],
    )

    open_clusters: list[dict[str, Any]] = []
    all_clusters: list[list[dict]] = []

    for d in detections:
        dtype = d["type"]
        ts = d["timestamp_offset_sec"]
        lat = d.get("lat")
        lng = d.get("lng")
        box = d.get("box_2d")

        still_open: list[dict[str, Any]] = []
        for c in open_clusters:
            if ts - c["last_ts"] > time_gap_s:
                all_clusters.append(c["members"])
            else:
                still_open.append(c)
        open_clusters = still_open

        matched: dict[str, Any] | None = None
        for c in open_clusters:
            if c["type"] != dtype:
                continue
            if use_gps and lat is not None and lng is not None \
                    and c["last_lat"] is not None and c["last_lng"] is not None:
                if _haversine_m(lat, lng, c["last_lat"], c["last_lng"]) <= gps_radius_m:
                    matched = c
                    break
            else:
                c_box = c.get("last_box")
                if box is None or c_box is None:
                    matched = c
                    break
                if _boxes_match(box, c_box):
                    matched = c
                    break

        if matched is not None:
            matched["members"].append(d)
            matched["last_ts"] = ts
            matched["last_lat"] = lat
            matched["last_lng"] = lng
            matched["last_box"] = box
        else:
            open_clusters.append({
                "type": dtype,
                "last_ts": ts,
                "last_lat": lat,
                "last_lng": lng,
                "last_box": box,
                "members": [d],
            })

    for c in open_clusters:
        all_clusters.append(c["members"])

    result: list[dict] = []
    for cluster in all_clusters:
        best = _pick_best(cluster, frames_dir, sharpness_floor)
        best["duplicate_count"] = len(cluster)
        result.append(best)

    n_in, n_out = len(detections), len(result)
    print(f"[dedupe] {n_in} detections -> {n_out} unique (removed {n_in - n_out} dupes)")

    result.sort(key=lambda d: d["priority"], reverse=True)
    report_dict["detections"] = result
    return report_dict
