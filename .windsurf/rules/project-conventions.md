---
trigger: always_on
description: Core conventions for the road-hazard-detector project
---

# Project conventions

- This is a road-condition analysis tool: dashcam frames from city vehicles ->
  hazard detections -> GPS-located, priority-scored map.
- **Never break the detection schema** in `detector/schema.py`. Every detection
  MUST keep `frame` and `timestamp_offset_sec` (the GPS join key) plus
  `priority` and `priority_label`.
- **Priority scoring stays deterministic in Python** (`detector/scoring.py`),
  never delegated to the LLM. Formula: `severity * road_weight * confidence`.
- Keep modules small and single-purpose under `detector/`. The CLI lives in
  `main.py`.
- Secrets come from `.env` via python-dotenv. Never hardcode keys. Update
  `.env.example` when adding a new env var.
- Pin new dependencies in `requirements.txt` with exact versions.
- Preserve the `--mock` capability end to end so the pipeline runs with no API
  key or footage (demo safety net).
- Match existing style: type hints, `from __future__ import annotations`,
  pydantic v2 models. Do not add comments unless they clarify non-obvious logic.
- After a meaningful change, ensure the mock run still works:
  `python main.py --input ./samples --mock`.
