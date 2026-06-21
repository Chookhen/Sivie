"""Deterministic priority scoring.

The vision model rates severity/confidence/road_context, but the final
priority number is computed here in Python so it is explainable and
reproducible (great for a demo: "here is exactly how we rank work orders").
"""

from __future__ import annotations

from .schema import PriorityLabel, RawIssue, RoadContext

ROAD_WEIGHT = {
    RoadContext.FREEWAY: 2.0,
    RoadContext.ARTERIAL: 1.5,
    RoadContext.RESIDENTIAL: 1.0,
    RoadContext.UNKNOWN: 1.2,
}


def compute_priority(issue: RawIssue) -> float:
    """priority = severity * road_weight * confidence (rounded to 2dp)."""
    weight = ROAD_WEIGHT.get(issue.road_context, 1.5)
    return round(issue.severity * weight * issue.confidence, 2)


def priority_label(priority: float) -> PriorityLabel:
    if priority >= 10:
        return PriorityLabel.CRITICAL
    if priority >= 6:
        return PriorityLabel.HIGH
    if priority >= 3:
        return PriorityLabel.MEDIUM
    return PriorityLabel.LOW
