"""Pydantic schemas for hazard detections and pipeline output.

These models are the contract between this detection engine and every
downstream module (GPS sync, scoring, map UI). Keep `frame` and
`timestamp_offset_sec` on every detection so a later module can join
detections to GPS coordinates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class IssueType(str, Enum):
    POTHOLE = "pothole"
    CRACK = "crack"
    OBSCURED_SIGN = "obscured_sign"
    FADED_MARKING = "faded_marking"
    DEBRIS = "debris"
    OTHER = "other"


class RoadContext(str, Enum):
    FREEWAY = "freeway"
    ARTERIAL = "arterial"
    RESIDENTIAL = "residential"
    UNKNOWN = "unknown"


class PriorityLabel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RawIssue(BaseModel):
    """A single issue exactly as returned by the vision model (pre-scoring)."""

    type: IssueType = IssueType.OTHER
    description: str = ""
    severity: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    road_context: RoadContext = RoadContext.UNKNOWN


class VisionResponse(BaseModel):
    """Top-level JSON the vision model must return for a single frame."""

    issues: List[RawIssue] = Field(default_factory=list)


class Detection(RawIssue):
    """A scored issue tied to a specific frame/timestamp."""

    frame: str
    timestamp_offset_sec: float
    priority: float = 0.0
    priority_label: PriorityLabel = PriorityLabel.LOW


class DetectionReport(BaseModel):
    """Final output document written to JSON."""

    source: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    frame_count: int = 0
    detections: List[Detection] = Field(default_factory=list)
