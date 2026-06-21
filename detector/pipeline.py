"""Orchestrates: frames -> blur filter -> vision -> scoring -> report."""

from __future__ import annotations

from typing import List, Optional

from .frame_extraction import Frame, get_frames, is_too_blurry
from .schema import Detection, DetectionReport
from .scoring import compute_priority, priority_label
from .vision_client import VisionClient


def run_pipeline(
    input_path: str,
    fps: float = 1.0,
    blur_threshold: float = 100.0,
    max_frames: Optional[int] = None,
    mock: bool = False,
    skip_blur_check: bool = False,
) -> DetectionReport:
    frames: List[Frame] = get_frames(input_path, fps)
    if max_frames is not None:
        frames = frames[:max_frames]

    print(f"[pipeline] {len(frames)} candidate frame(s) from {input_path}")

    client = VisionClient(mock=mock)
    report = DetectionReport(source=input_path, frame_count=len(frames))

    skipped_blur = 0
    failed = 0

    for i, frame in enumerate(frames, start=1):
        if not skip_blur_check and not mock and is_too_blurry(frame.path, blur_threshold):
            skipped_blur += 1
            continue

        try:
            vision = client.analyze(frame.path)
        except Exception as exc:  # noqa: BLE001 - log + continue
            failed += 1
            print(f"[pipeline] WARN frame {frame.name} failed: {exc}")
            continue

        for issue in vision.issues:
            priority = compute_priority(issue)
            report.detections.append(
                Detection(
                    **issue.model_dump(),
                    frame=frame.name,
                    timestamp_offset_sec=frame.timestamp_offset_sec,
                    priority=priority,
                    priority_label=priority_label(priority),
                )
            )

        if i % 10 == 0 or i == len(frames):
            print(f"[pipeline] processed {i}/{len(frames)} | detections so far: {len(report.detections)}")

    report.detections.sort(key=lambda d: d.priority, reverse=True)

    print(
        f"[pipeline] done. detections={len(report.detections)} "
        f"blurry_skipped={skipped_blur} failed={failed}"
    )
    return report
