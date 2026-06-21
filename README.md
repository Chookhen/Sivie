# Sivie — AI Road Integrity Operations

> Government-grade road-hazard intelligence: detect infrastructure defects from
> vehicle footage, geolocate them on a live map, rank them by an explainable
> priority score, and manage them as work orders in a persistent database.

Sivie turns ordinary dashcam / phone video + a GPS track into a prioritized,
mapped, auditable hazard database. A computer-vision pipeline finds potholes,
cracks, obscured signs, faded markings and debris; each detection is geolocated,
enriched with the real street name, deduplicated across passes, and scored with a
**deterministic, explainable** priority formula (optionally adjusted by a Gemini
vision model). A React operations console visualizes everything: a severity-colored
map, an editable operations database, an analysis review board, and a one-click
**Processing** page that runs the whole pipeline from the browser.

---

## Quick start

The fastest way to see Sivie running end-to-end — **mock mode, no API keys, no
footage, ~3 minutes**. Copy-paste each block in order.

**Prerequisites:** Python 3.9+, Node 18+, [`ffmpeg`](https://ffmpeg.org/) and `git`.

```bash
# 1 · Clone the repo
git clone https://github.com/Chookhen/road-hazard-detector.git
cd road-hazard-detector

# 2 · Install the Python pipeline + API
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3 · Generate demo data with the MOCK detector (no keys / no video needed)
python main.py --input ./samples --mock \
  --save-frames-dir web/public/frames --output web/public/detections.json
```

```bash
# 4 · Start the backend API  (keep this terminal open)
uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# 5 · Load the generated data into the operations DB
curl -X POST http://localhost:8000/api/reseed

# 6 · Start the web console  (new terminal, from the repo root)
cd web && npm install && npm run dev
```

Open **http://localhost:5173** — the Map, Operations DB, Analysis and Processing
tabs are now live.

> **Map tiles** need a free [Mapbox token](https://account.mapbox.com/access-tokens/):
> create `web/.env` with `VITE_MAPBOX_TOKEN=pk....`. The Operations DB and Analysis
> tabs work fully without it.
>
> **Real AI** (instead of `--mock`): add a `GEMINI_API_KEY` to `.env` (see
> [Getting started](#getting-started)) and run with `--detector yolo --enrich
> --ai-priority` — or just use the in-app **Processing** tab.

---

## Highlights

- **End-to-end pipeline** — video → frames → detection → GPS sync → street
  enrichment → dedupe/aggregation → priority scoring → JSON.
- **Two detectors** — local **YOLOv11** (RDD2022 road-damage weights) or
  **Gemini** vision; swap with one flag.
- **Exact geolocation** — automatic video↔GPX time synchronization (with a
  tunable offset) interpolates a lat/lng for every detection. Footage without a
  track is stored with no coordinates and simply shows no map markers.
- **Explainable priority** — a transparent Python formula (`severity × road_weight
  × confidence`), optionally multiplied by a Gemini urgency assessment that
  returns human-readable justifications.
- **Street-level aggregation** — a persistent hazard DB deduplicates repeat
  sightings and rolls hazards up per street, so chronically damaged roads rise in
  priority.
- **Operations console** — severity-colored Mapbox map (white 0–4, orange 4–7,
  red 7–10), CRUD operations database, analysis review, and an in-browser
  **Processing** page with live job logs.
- **Pluggable storage** — Supabase Postgres when configured, local JSON otherwise.

---

## Architecture

```
                ┌─────────────────────────── detector/ (Python pipeline) ───────────────────────────┐
  video/GPX ──▶ │ frame_extraction → yolo_client / vision_client → scoring                            │
                │        │                                   │                                          │
                │        └─▶ gps_sync (auto time-align) ─────┴─▶ osm_context (street name + POIs)       │
                │                          │                                                            │
                │              street_registry (persistent dedupe + per-street rollup)                  │
                │                          │                                                            │
                │              gemini_priority (optional urgency multiplier + justification)            │
                └──────────────────────────┬─────────────────────────────────────────────────────────┘
                                           ▼
                              web/public/detections.json
                                           │
        ┌──────────────────────────────────┼───────────────────────────────────┐
        ▼                                   ▼                                     ▼
  server/ (FastAPI)                React console (web/)                  Processing page
  CRUD occurrences DB     map · operations DB · analysis review     runs the pipeline as a
  (Supabase | JSON)           (Mapbox GL + Tailwind)                background job w/ live log
```

---

## Tech stack

| Layer | Tech |
|-------|------|
| Detection | Ultralytics YOLOv11 (RDD2022), Google Gemini, OpenCV, PyTorch |
| Pipeline | Python 3.9+, Pydantic, ffmpeg, gpxpy, OSM Overpass/Nominatim |
| Backend | FastAPI, Uvicorn, Supabase (optional) |
| Frontend | React + TypeScript, Vite, Tailwind CSS, Mapbox GL, Lucide |

---

## Project structure

```
road-hazard-detector/
├── main.py                     # CLI entrypoint for the pipeline
├── requirements.txt
├── detector/                   # Computer-vision + scoring pipeline
│   ├── pipeline.py             #   orchestration
│   ├── frame_extraction.py     #   ffmpeg sampling + blur filtering
│   ├── yolo_client.py          #   YOLOv11 road-damage detector
│   ├── vision_client.py        #   Gemini vision detector + mock mode
│   ├── gps_sync.py             #   video↔GPX auto time-sync + interpolation
│   ├── osm_context.py          #   reverse-geocode street name + nearby POIs
│   ├── street_registry.py      #   persistent hazard DB + per-street rollup
│   ├── dedupe.py               #   cross-frame de-duplication
│   ├── scoring.py              #   explainable priority formula
│   ├── gemini_priority.py      #   optional AI urgency multiplier
│   └── schema.py               #   Pydantic contracts
├── server/                     # FastAPI operations backend
│   ├── app.py                  #   occurrences CRUD + files/upload/process routes
│   ├── jobs.py                 #   background pipeline job runner (live logs)
│   ├── store.py                #   pluggable storage (Supabase | JSON)
│   └── models.py
└── web/                        # React + TypeScript operations console
    └── src/
        ├── App.tsx
        ├── components/         # NavBar, MapView, Sidebar, StatsPanel
        └── pages/              # DatabasePage, AnalysisPage, ProcessingPage
```

---

## Getting started

### 1. Pipeline + backend (Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg            # macOS (required for video input)

cp .env.example .env           # then fill in keys (see below)
```

`.env` keys (all optional for a mock run):

```
GEMINI_API_KEY=...             # for Gemini detection / AI priority — aistudio.google.com/app/apikey
SUPABASE_URL=...               # optional; falls back to local JSON storage
SUPABASE_KEY=...
```

Start the API:

```bash
uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend (React)

```bash
cd web
npm install
# add web/.env with VITE_MAPBOX_TOKEN=pk.... for the map
npm run dev                    # http://localhost:5173
```

---

## Running the pipeline

**From the browser (recommended):** open the **Processing** tab, pick a video and
optional GPS track from the connected directory (or upload your own), set options
(the GPS offset defaults to `-3s`), and click **Run pipeline**. The job streams its
log live and refreshes the map + operations DB when it finishes.

**From the CLI:**

```bash
# Mock run — no key or footage needed
python main.py --input ./samples --mock

# Real run with YOLO + GPS + street enrichment + AI priority
python main.py \
  --input test_images/berkeley.mp4 --gpx test_images/berkeley2.gpx \
  --detector yolo --fps 1 --dedupe --enrich --ai-priority \
  --time-offset -3 --save-frames-dir web/public/frames \
  --output web/public/detections.json
```

Key flags: `--detector {yolo,gemini}`, `--fps`, `--max-frames`, `--gpx`,
`--time-offset`, `--no-auto-sync`, `--dedupe`, `--enrich`, `--ai-priority`,
`--mock`. Run `python main.py --help` for the full list.

---

## Priority scoring

The base priority is computed in Python (not by the model) so it is deterministic,
auditable and explainable:

```
priority   = severity (1–5) × road_weight × confidence (0–1)
road_weight= { freeway: 2.0, arterial: 1.5, residential: 1.0, unknown: 1.2 }
label      = >=10 CRITICAL · >=6 HIGH · >=3 MEDIUM · else LOW
```

When `--ai-priority` is enabled, Gemini reviews the annotated frame + context and
returns an urgency **multiplier** (0.5–2.0) plus short justifications:

```
final_priority = priority × multiplier
```

The map colors markers by this score: white (0–4), orange (4–7), red (7–10).

---

## Backend API

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/health` | Backend status + active storage type |
| `GET` | `/api/occurrences` | List hazard occurrences |
| `POST` | `/api/occurrences` | Create an occurrence |
| `DELETE` | `/api/occurrences/{id}` | Delete an occurrence |
| `POST` | `/api/reseed` | Rebuild the DB from `detections.json` |
| `GET` | `/api/files` | List selectable video/GPS source files |
| `POST` | `/api/upload` | Upload a video or GPS file |
| `POST` | `/api/process` | Start a pipeline run (background job) |
| `GET` | `/api/process/{id}` | Poll job status + stream log lines |

---

## Notes

- Generated artifacts (`web/public/detections.json`, extracted `frames/`, uploads,
  local DB caches) and secrets (`.env`) are git-ignored — clone the repo, add your
  keys, and run the pipeline to populate data.
- A full run over a multi-minute video takes several minutes; use `--max-frames`
  (or the Processing page's options) for a fast demo.
