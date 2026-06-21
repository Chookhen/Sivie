"""Gemini vision client.

Sends a frame to Gemini (model set by MODEL_NAME) and returns a validated
VisionResponse. Images are sent as inline bytes (the File API rejects some
key formats), which is also faster and avoids upload quota.
Includes a deterministic-ish `mock` mode so the full pipeline runs end to
end with no API key or footage (useful for building/testing the UI and the
scoring, and as a demo-day safety net).
"""

from __future__ import annotations

import json
import mimetypes
import os
import random
import re
import time
from typing import Optional

from .schema import VisionResponse

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

INSTRUCTION = """You are a municipal road-infrastructure inspector reviewing a
single dashcam frame from a city vehicle. Your job is ACCURATE assessment, not
finding problems.

Most frames show roads in normal, serviceable condition. For such frames the
correct answer is an empty list. Do NOT feel obligated to report anything:
reporting a defect that is not clearly present is a serious error. Prefer a
false negative over a false positive — it is better to miss a marginal defect
than to invent one.

Report ONLY clear, safety-relevant defects you can directly see in THIS image.
Never infer, assume, or guess. Allowed issue types and the bar for each:

- pothole: an actual hole or cavity in the road surface. Not a shadow, patch,
  manhole cover, or stain.
- crack: SIGNIFICANT pavement cracking — alligator/network cracking, wide or
  open cracks, or clearly deteriorating surface. NOT hairline cracks, expansion
  joints, or normal surface texture. CRITICAL: a crack that has been filled or
  sealed (a line of black tar/sealant, or a different-colored filler tracing the
  crack shape) is ALREADY REPAIRED — do NOT report it; it is not an active
  defect.
- obscured_sign: ONLY a regulatory or warning sign (stop, yield, speed limit,
  do-not-enter, one-way, school/pedestrian/curve warning) so obscured that a
  driver could miss critical safety information. EXCLUDE street-name signs,
  parking/permit signs, business/information signs, and any sign that is merely
  near foliage or only slightly overlapped.
- faded_marking: lane lines, crosswalks, or stop bars worn enough to materially
  reduce visibility. NOT lightly weathered paint.
- debris: an object in the travel lane that poses a hazard.
- other: a clear safety hazard not covered above.

LOCATION RULE: pothole, crack, and faded_marking are ROAD-SURFACE defects and
can ONLY appear on the paved road, which is the lower portion of the frame.
NEVER report them in the sky, on buildings, trees, poles, wires, vehicles, or
anywhere above the road surface. If a candidate is not clearly on the pavement,
do not report it.

For road_context, infer from visual cues (lane count, speed-limit signs,
sidewalks, buildings, medians):
- freeway: high-speed, multi-lane, no pedestrians
- arterial: major city road, moderate speed
- residential: local street, houses, low speed
- unknown: cannot tell

Rate severity 1-5 (1=cosmetic, 5=immediate safety hazard). Set confidence
0.0-1.0 to reflect your genuine visual certainty that the defect is real and
matches its category; do not inflate it. Only report issues you are genuinely
confident about.

For each issue, include box_2d: [ymin, xmin, ymax, xmax] normalized 0-1000.
The box must be TIGHT: the smallest rectangle that contains the actual defect,
NOT the general road area. For a defect spread over an area (e.g. cracking), box
the single worst, most concentrated patch, not the whole road. The box must
contain ONLY the defect itself — never include sky, buildings, sidewalks,
vehicles, or large stretches of intact pavement. If it cannot be precisely
localized, set box_2d to null.

Return ONLY valid JSON, no markdown, matching exactly:
{"issues": [{"type": "...", "description": "...", "severity": 1-5,
"confidence": 0.0-1.0, "road_context": "...", "box_2d": [ymin, xmin, ymax, xmax]}]}
If no clear defects are visible, return {"issues": []}.
"""

_MOCK_TYPES = ["pothole", "crack", "obscured_sign", "faded_marking", "debris"]
_MOCK_CONTEXTS = ["freeway", "arterial", "residential"]


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def mock_response(seed_key: str) -> VisionResponse:
    """Generate plausible, stable-per-frame fake detections."""
    rng = random.Random(seed_key)
    if rng.random() < 0.35:
        return VisionResponse(issues=[])
    n = rng.randint(1, 2)
    issues = []
    for _ in range(n):
        ymin = rng.randint(420, 580)
        xmin = rng.randint(150, 430)
        ymax = min(1000, ymin + rng.randint(80, 220))
        xmax = min(1000, xmin + rng.randint(120, 320))
        issues.append(
            {
                "type": rng.choice(_MOCK_TYPES),
                "description": "Auto-generated mock detection for pipeline testing.",
                "severity": rng.randint(1, 5),
                "confidence": round(rng.uniform(0.55, 0.97), 2),
                "road_context": rng.choice(_MOCK_CONTEXTS),
                "box_2d": [ymin, xmin, ymax, xmax],
            }
        )
    return VisionResponse(issues=issues)


class VisionClient:
    def __init__(self, mock: bool = False, api_key: Optional[str] = None,
                 temperature: float = 0.0):
        self.mock = mock
        self.temperature = temperature
        self._model = None
        if not mock:
            api_key = api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY not set. Add it to .env or run with --mock."
                )
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            gen_cfg: dict = {
                "temperature": temperature,
                "response_mime_type": "application/json",
            }
            self._model = genai.GenerativeModel(
                MODEL_NAME,
                system_instruction=INSTRUCTION,
                generation_config=gen_cfg,
            )

    def analyze(self, image_path: str) -> VisionResponse:
        if self.mock:
            return mock_response(os.path.basename(image_path))
        return self._analyze_real(image_path)

    def _analyze_real(self, image_path: str) -> VisionResponse:
        with open(image_path, "rb") as fh:
            data = fh.read()
        mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        for attempt in range(1, 4):
            try:
                resp = self._model.generate_content(
                    [{"mime_type": mime_type, "data": data}, "Analyze this frame."]
                )
                raw = _strip_code_fences(resp.text or "{}")
                return VisionResponse.model_validate(json.loads(raw))
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "429" in msg or "ResourceExhausted" in msg or "RESOURCE_EXHAUSTED" in msg:
                    wait = 45
                    m = re.search(r'retry in (\d+)', msg)
                    if m:
                        wait = int(m.group(1)) + 3
                    if attempt < 3:
                        print(f"[vision] rate-limited, waiting {wait}s before retry {attempt}/3…")
                        time.sleep(wait)
                        continue
                raise
        raise RuntimeError("exhausted retries")
