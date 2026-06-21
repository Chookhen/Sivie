# road-hazard-detector

Detection engine for an AI road-condition mapping project: analyze dashcam
frames from city/government vehicles, detect public-infrastructure hazards
(potholes, cracks, obscured signs, faded markings, debris), score each by
priority, and emit a structured JSON that downstream modules (GPS sync,
map UI) consume.

This is **stage 1** of the project: a standalone CLI. It deliberately keeps
`frame` + `timestamp_offset_sec` on every detection so a later module can
join detections to a GPS track by time.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`ffmpeg` must be installed for video input:

```bash
brew install ffmpeg   # macOS
```

Add your key (only needed for real, non-mock runs):

```bash
cp .env.example .env   # then edit .env and paste your GEMINI_API_KEY
```

Get a key at https://aistudio.google.com/app/apikey

## Usage

Mock mode (no API key or footage needed — runs the full pipeline on the
bundled placeholder frames):

```bash
python main.py --input ./samples --mock
```

Real run on a video:

```bash
python main.py --input drive.mov --fps 1 --output detections.json
```

Real run on a folder of frames, capped for cost while testing:

```bash
python main.py --input ./frames --max-frames 20
```

### Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--input` | (required) | Video file or image folder |
| `--fps` | 1.0 | Frames/sec to extract (video only) |
| `--output` | detections.json | Output path |
| `--max-frames` | none | Cap frames (testing/cost) |
| `--blur-threshold` | 100.0 | Skip frames below this Laplacian variance |
| `--mock` | off | Fake detections, no API needed |
| `--skip-blur-check` | off | Disable blur filter |

## Output

```json
{
  "source": "drive.mov",
  "generated_at": "2026-...Z",
  "frame_count": 120,
  "detections": [
    {
      "frame": "frame_00007.jpg",
      "timestamp_offset_sec": 7.0,
      "type": "pothole",
      "description": "...",
      "severity": 4,
      "confidence": 0.88,
      "road_context": "arterial",
      "priority": 7.04,
      "priority_label": "HIGH"
    }
  ]
}
```

## Priority scoring

```
priority = severity * road_weight * confidence
road_weight = { freeway: 3.0, arterial: 2.0, residential: 1.0, unknown: 1.5 }
label: >=10 CRITICAL, >=6 HIGH, >=3 MEDIUM, else LOW
```

Scoring is computed in Python (not by the model) so it is deterministic and
explainable.

## Next stages (not in this module)

- **gps_sync**: join `timestamp_offset_sec` to a GPX track -> lat/lng.
- **map UI**: React + Mapbox, color-coded priority pins + heatmap + work-order list.

## Project layout

```
detector/
  schema.py            # pydantic contracts
  frame_extraction.py  # ffmpeg + folder + blur check
  vision_client.py     # Gemini 2.0 Flash + mock mode
  scoring.py           # priority formula
  pipeline.py          # orchestration
main.py                # CLI
samples/               # placeholder frames for --mock
```
