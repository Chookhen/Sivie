"""Pydantic models shared by the operations-DB API and its storage backends."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 1)


class Occurrence(BaseModel):
    id: str
    type: str
    description: str = ""
    severity: int = 3                      # detector severity, 1-5
    score: float = 0.0                     # 0-10 urgency, drives map colour
    confidence: Optional[float] = None
    road_name: Optional[str] = None
    road_context: Optional[str] = None
    frame: Optional[str] = None
    image_url: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    justification: List[str] = Field(default_factory=list)
    priority_multiplier: Optional[float] = None
    times_seen: int = 1
    source: str = "detection"              # detection | manual
    status: str = "open"                   # open | resolved
    created_at: str = Field(default_factory=now_iso)


class OccurrenceCreate(BaseModel):
    type: str = "pothole"
    description: str = ""
    severity: int = 3
    score: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    road_name: Optional[str] = None
    road_context: Optional[str] = None


class OccurrenceUpdate(BaseModel):
    severity: Optional[int] = None
    score: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    road_name: Optional[str] = None
