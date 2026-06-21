"""Gemini vision client.

Sends a frame to Gemini 2.0 Flash and returns a validated VisionResponse.
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
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from .schema import VisionResponse

MODEL_NAME = "gemini-2.5-flash"

INSTRUCTION = """You are a municipal road-infrastructure inspector reviewing a
single dashcam frame captured from a city vehicle.

Identify visible public-infrastructure hazards. Allowed issue types:
pothole, crack, obscured_sign, faded_marking, debris, other.

For road_context, infer from visual cues (lane count, speed-limit signs,
sidewalks, buildings, medians):
- freeway: high-speed, multi-lane, no pedestrians
- arterial: major city road, moderate speed
- residential: local street, houses, low speed
- unknown: cannot tell

Rate severity 1-5 (1=cosmetic, 5=immediate safety hazard) and confidence
0.0-1.0. Be conservative with confidence.

Return ONLY valid JSON, no markdown, matching exactly:
{"issues": [{"type": "...", "description": "...", "severity": 1-5,
"confidence": 0.0-1.0, "road_context": "..."}]}
If no issues are visible, return {"issues": []}.
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
        issues.append(
            {
                "type": rng.choice(_MOCK_TYPES),
                "description": "Auto-generated mock detection for pipeline testing.",
                "severity": rng.randint(1, 5),
                "confidence": round(rng.uniform(0.55, 0.97), 2),
                "road_context": rng.choice(_MOCK_CONTEXTS),
            }
        )
    return VisionResponse(issues=issues)


class VisionClient:
    def __init__(self, mock: bool = False, api_key: Optional[str] = None,
                 temperature: float = 0.2):
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
            self._model = genai.GenerativeModel(
                MODEL_NAME,
                system_instruction=INSTRUCTION,
                generation_config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
            )

    def analyze(self, image_path: str) -> VisionResponse:
        if self.mock:
            return mock_response(os.path.basename(image_path))
        return self._analyze_real(image_path)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _analyze_real(self, image_path: str) -> VisionResponse:
        with open(image_path, "rb") as fh:
            data = fh.read()
        mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        resp = self._model.generate_content(
            [{"mime_type": mime_type, "data": data}, "Analyze this frame."]
        )
        raw = _strip_code_fences(resp.text or "{}")
        return VisionResponse.model_validate(json.loads(raw))
