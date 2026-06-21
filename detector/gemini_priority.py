"""Gemini 2.5 Pro urgency evaluator (the "judgment" layer).

YOLO says WHAT and WHERE; the deterministic scorer gives an explainable
baseline; this module asks Gemini 2.5 Pro to reason about real-world urgency
using the full scene plus structured context (road class, nearby
schools/hospitals/crossings, and how many hazards are already logged on this
street). It returns a bounded multiplier on the baseline plus a few concise
reasons that the UI surfaces when you click a hazard's score.

Design choices:
- We send the FULL frame with the hazard's box drawn on it, so Gemini can see
  the surrounding context (road type, signage, environment) — not just a crop.
- Gemini outputs a MULTIPLIER (0.5-2.5), not an absolute score, so the final
  number stays anchored to the explainable baseline: final = baseline x mult.
- One call per UNIQUE (deduped) detection, so cost is ~dozens of calls/video.
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from typing import Any, Optional

from .scoring import priority_label

PRIORITY_MODEL = os.getenv("GEMINI_PRIORITY_MODEL", "gemini-2.5-pro")

INSTRUCTION = """You are a senior municipal road-maintenance triage engineer.
You are shown a single dashcam frame in which ONE road hazard has been
highlighted with a colored rectangle, together with structured context. A
deterministic baseline priority has already been computed. Your job is to
decide how much to SCALE that baseline up or down based on real-world repair
urgency, and to justify it concisely.

Weigh factors such as:
- Road class / setting: freeways and busy arterials carry far more (and faster)
  traffic than quiet residential streets -> higher urgency.
- Vulnerable nearby land use: schools, kindergartens, hospitals, and pedestrian
  crossings raise the cost of an accident -> higher urgency.
- Hazard type and apparent size/depth in the image: a deep open pothole in a
  travel lane is far more urgent than a thin surface crack.
- Street history: if many hazards are already logged on this street, the road
  is failing systemically -> raise urgency.
- Mitigating signs: if the hazard looks minor, off to the shoulder, or already
  patched, scale DOWN.

Return ONLY valid JSON, no markdown:
{"multiplier": <float between 0.5 and 2.5>,
 "reasons": ["concise reason <= 12 words", "..."]}
Provide 2 to 4 reasons. Each must be specific to THIS hazard and its context.
Do not restate the raw numbers; explain the judgment.
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _annotated_frame_bytes(frame_path: str, box_2d: Optional[list[int]]) -> Optional[bytes]:
    """Return JPEG bytes of the frame with the hazard box drawn, downscaled."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    if not os.path.exists(frame_path):
        return None
    img = Image.open(frame_path).convert("RGB")
    w, h = img.size
    if box_2d:
        ymin, xmin, ymax, xmax = box_2d
        left, top = xmin / 1000 * w, ymin / 1000 * h
        right, bottom = xmax / 1000 * w, ymax / 1000 * h
        draw = ImageDraw.Draw(img)
        line = max(3, int(min(w, h) * 0.006))
        draw.rectangle([left, top, right, bottom], outline=(255, 40, 40), width=line)
    # Downscale to keep token cost down while preserving context.
    max_dim = 1024
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _context_text(det: dict) -> str:
    pois = det.get("nearby_pois") or []
    poi_str = (
        ", ".join(f"{p.get('name') or p.get('category')} ({p.get('distance_m')}m)" for p in pois[:5])
        if pois else "none detected nearby"
    )
    return (
        f"Hazard type: {det.get('type')}\n"
        f"Detector severity (1-5): {det.get('severity')}\n"
        f"Detector confidence: {det.get('confidence')}\n"
        f"Baseline priority: {det.get('priority')}\n"
        f"Road name: {det.get('road_name') or 'unknown'}\n"
        f"Road class (OSM): {det.get('road_class') or 'unknown'}\n"
        f"Inferred road context: {det.get('road_context')}\n"
        f"Nearby points of interest: {poi_str}\n"
        f"Hazards already logged on this street: "
        f"{det.get('street_hazard_count') or 1} "
        f"(potholes={det.get('street_pothole_count') or 0}, "
        f"cracks={det.get('street_crack_count') or 0})\n"
        f"Times this exact hazard has been observed: {det.get('times_seen') or 1}\n"
    )


def _mock_eval(det: dict) -> dict[str, Any]:
    import random

    rng = random.Random(det.get("frame", "") + str(det.get("box_2d")))
    mult = round(rng.uniform(0.7, 1.8), 2)
    reasons = [
        f"{det.get('type', 'hazard').capitalize()} on {det.get('road_name') or 'roadway'}",
        "Near pedestrian activity" if rng.random() < 0.5 else "Moderate traffic exposure",
        f"{det.get('street_hazard_count') or 1} hazard(s) logged on street",
    ]
    return {"multiplier": mult, "reasons": reasons}


class PriorityEvaluator:
    def __init__(self, mock: bool = False, api_key: Optional[str] = None,
                 model: Optional[str] = None, frames_dir: Optional[str] = None):
        self.mock = mock
        self.frames_dir = frames_dir
        self.model_name = model or PRIORITY_MODEL
        self._model = None
        if mock:
            return
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set. Add it to .env or run with --mock.")
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            self.model_name,
            system_instruction=INSTRUCTION,
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        )

    def evaluate(self, det: dict) -> dict[str, Any]:
        if self.mock:
            return _mock_eval(det)
        parts: list[Any] = []
        if self.frames_dir and det.get("frame"):
            img_bytes = _annotated_frame_bytes(
                os.path.join(self.frames_dir, det["frame"]), det.get("box_2d")
            )
            if img_bytes:
                parts.append({"mime_type": "image/jpeg", "data": img_bytes})
        parts.append(_context_text(det))
        parts.append("Assess this hazard's repair urgency and return the JSON.")

        for attempt in range(1, 4):
            try:
                resp = self._model.generate_content(parts)
                data = json.loads(_strip_code_fences(resp.text or "{}"))
                mult = float(data.get("multiplier", 1.0))
                mult = max(0.5, min(2.0, mult))
                reasons = [str(r) for r in (data.get("reasons") or [])][:4]
                return {"multiplier": round(mult, 2), "reasons": reasons}
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if ("429" in msg or "ResourceExhausted" in msg) and attempt < 3:
                    wait = 30
                    m = re.search(r"retry in (\d+)", msg)
                    if m:
                        wait = int(m.group(1)) + 3
                    print(f"[priority] rate-limited, waiting {wait}s (retry {attempt}/3)…")
                    time.sleep(wait)
                    continue
                print(f"[priority] WARN eval failed for {det.get('frame')}: {exc}")
                return {"multiplier": 1.0, "reasons": []}
        return {"multiplier": 1.0, "reasons": []}


def _sort_key(d: dict) -> float:
    fp = d.get("final_priority")
    return fp if fp is not None else d.get("priority", 0.0)


def evaluate_report(
    report_dict: dict,
    frames_dir: Optional[str] = None,
    mock: bool = False,
    model: Optional[str] = None,
    max_items: Optional[int] = None,
    save_path: Optional[str] = None,
    save_every: int = 3,
) -> dict:
    """Run Gemini urgency evaluation over each detection, in priority order.

    If ``save_path`` is given, the (re-sorted) report is checkpointed to disk
    every ``save_every`` evaluations so progress is visible in the UI and a
    kill never loses completed work.
    """
    evaluator = PriorityEvaluator(mock=mock, model=model, frames_dir=frames_dir)
    dets = sorted(report_dict.get("detections", []), key=lambda d: d.get("priority", 0), reverse=True)
    # Seed every detection's final_priority with its baseline so unevaluated
    # (or capped) items still rank sensibly.
    for det in dets:
        det.setdefault("final_priority", det.get("priority"))
    todo = dets if max_items is None else dets[:max_items]
    print(f"[priority] evaluating {len(todo)} detection(s) with {evaluator.model_name}"
          f"{' (mock)' if mock else ''}")

    def _checkpoint() -> None:
        if not save_path:
            return
        report_dict["detections"] = sorted(dets, key=_sort_key, reverse=True)
        with open(save_path, "w", encoding="utf-8") as fh:
            json.dump(report_dict, fh, indent=2)

    for i, det in enumerate(dets, start=1):
        if max_items is not None and i > max_items:
            continue
        result = evaluator.evaluate(det)
        mult = result["multiplier"]
        baseline = det.get("priority", 0.0)
        final = round(baseline * mult, 2)
        det["priority_multiplier"] = mult
        det["final_priority"] = final
        det["justification"] = result["reasons"]
        det["priority_label"] = priority_label(final).value
        if i % save_every == 0:
            _checkpoint()
        if i % 5 == 0 or i == len(todo):
            print(f"[priority] {i}/{len(todo)} | x{mult} -> {final}")

    report_dict["detections"] = sorted(dets, key=_sort_key, reverse=True)
    _checkpoint()
    return report_dict
