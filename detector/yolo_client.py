"""Local YOLO road-damage detector.

Drop-in replacement for VisionClient: exposes the same
`analyze(image_path) -> VisionResponse` contract so the rest of the pipeline
is unchanged. Unlike the Gemini VLM, a purpose-built object detector produces
TIGHT, consistent bounding boxes and runs locally (no API cost, no rate limits,
milliseconds per frame).

Default weights: `rezzzq/yolo12s-road-damage-rdd2022` — trained on the RDD2022
Global Road Damage Detection benchmark. Classes:
    D00 = longitudinal crack
    D10 = transverse crack
    D20 = alligator / network crack
    D40 = pothole
    Repair = already-repaired surface  (ignored — not an active defect)

Boxes come out of YOLO as pixel xyxy; we normalise to the 0-1000
[ymin, xmin, ymax, xmax] convention the schema/frontend already expect.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from .schema import IssueType, RawIssue, RoadContext, VisionResponse

DEFAULT_REPO = os.getenv("YOLO_REPO", "Nothingger/RDD_YOLO_pretrained")
DEFAULT_FILE = os.getenv("YOLO_FILE", "YOLOv11x_RDD_Trained.pt")

# Map raw model class names -> (IssueType, base severity 1-5, human label).
# Keyed case-insensitively; covers the RDD2022 D-codes and the common
# spelled-out variants used by other road-damage checkpoints.
_CLASS_MAP: Dict[str, Tuple[IssueType, int, str]] = {
    "d00": (IssueType.CRACK, 2, "Longitudinal crack"),
    "d10": (IssueType.CRACK, 2, "Transverse crack"),
    "d20": (IssueType.CRACK, 3, "Alligator (network) cracking"),
    "d40": (IssueType.POTHOLE, 4, "Pothole"),
    "longitudinal crack": (IssueType.CRACK, 2, "Longitudinal crack"),
    "transverse crack": (IssueType.CRACK, 2, "Transverse crack"),
    "alligator crack": (IssueType.CRACK, 3, "Alligator (network) cracking"),
    "pothole": (IssueType.POTHOLE, 4, "Pothole"),
    "potholes": (IssueType.POTHOLE, 4, "Pothole"),
}

# Classes we explicitly ignore (already-repaired surface is not a defect).
_IGNORE = {"repair", "other corruption"}


def _severity_for(base: int, conf: float) -> int:
    """Nudge base severity up for very high-confidence detections."""
    sev = base
    if conf >= 0.8:
        sev += 1
    return max(1, min(5, sev))


class YoloClient:
    """Runs a local YOLO road-damage model and returns a VisionResponse."""

    def __init__(
        self,
        mock: bool = False,
        repo: Optional[str] = None,
        weights_file: Optional[str] = None,
        conf: float = 0.25,
        iou: float = 0.45,
    ):
        self.mock = mock
        self.conf = conf
        self.iou = iou
        self._model = None
        self.names: Dict[int, str] = {}
        if mock:
            # Reuse the VLM mock generator for parity in mock runs.
            return
        repo = repo or DEFAULT_REPO
        weights_file = weights_file or DEFAULT_FILE
        try:
            from huggingface_hub import hf_hub_download
            from ultralytics import YOLO
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError(
                "YOLO detector needs `ultralytics` and `huggingface_hub`. "
                "Install with: pip install ultralytics huggingface_hub"
            ) from exc

        # Allow a local .pt path to bypass the HF download entirely.
        local = os.getenv("YOLO_WEIGHTS")
        weights_path = local if local and os.path.exists(local) else hf_hub_download(
            repo_id=repo, filename=weights_file
        )
        self._model = YOLO(weights_path)
        self.names = dict(self._model.names)
        print(f"[yolo] loaded {repo} | classes={list(self.names.values())}")

    def analyze(self, image_path: str) -> VisionResponse:
        if self.mock:
            from .vision_client import mock_response

            return mock_response(os.path.basename(image_path))
        return self._analyze_real(image_path)

    def _analyze_real(self, image_path: str) -> VisionResponse:
        result = self._model.predict(
            image_path, conf=self.conf, iou=self.iou, verbose=False
        )[0]
        if result.boxes is None or len(result.boxes) == 0:
            return VisionResponse(issues=[])

        height, width = result.orig_shape  # (H, W)
        issues = []
        for box in result.boxes:
            raw_name = self.names.get(int(box.cls), "").strip()
            key = raw_name.lower()
            if key in _IGNORE:
                continue
            mapped = _CLASS_MAP.get(key)
            if mapped is None:
                issue_type, base_sev, label = IssueType.OTHER, 2, raw_name or "Road defect"
            else:
                issue_type, base_sev, label = mapped

            conf = float(box.conf)
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            box_2d = [
                max(0, min(1000, round(y1 / height * 1000))),
                max(0, min(1000, round(x1 / width * 1000))),
                max(0, min(1000, round(y2 / height * 1000))),
                max(0, min(1000, round(x2 / width * 1000))),
            ]
            issues.append(
                RawIssue(
                    type=issue_type,
                    description=f"{label} (auto-detected, {conf:.0%} confidence).",
                    severity=_severity_for(base_sev, conf),
                    confidence=round(conf, 3),
                    road_context=RoadContext.UNKNOWN,
                    box_2d=box_2d,
                )
            )
        return VisionResponse(issues=issues)
