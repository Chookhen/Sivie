# Project Context — Road Hazard Detector

> Source-of-truth context for writing the Devpost. Everything below reflects what
> the codebase actually does (not aspirational).

## One-line pitch
An AI pipeline that turns ordinary dashcam/drive footage into a prioritized,
map-based road-hazard database that a city or government operations team can
review, edit, and act on.

## The problem
Road maintenance is reactive and manual. Potholes, cracks, faded lane markings,
obscured signs, and debris are mostly reported by citizens after they become
dangerous. Cities have no cheap, continuous way to:
- detect hazards at scale from footage they already capture,
- decide *which* ones to fix first (triage), and
- keep an authoritative, queryable record of where hazards are.

## What it does
1. **Detects** road damage in video/image footage using a YOLO road-damage model.
2. **Scores** each hazard for urgency, then re-ranks with a Gemini 2.5 Pro
   "triage" pass that adds a priority multiplier + short human-readable reasons.
3. **Locates** hazards on a map (when GPS is available) and **aggregates by
   street** so repeat problems on the same road raise priority.
4. **Stores** everything in a government-operations database (Supabase Postgres)
   with full add / edit / remove (CRUD), exposed through a clean web UI.
5. **Visualizes** results on a severity-colored map and an analyst review page.

## How it works (pipeline)
The CLI (`main.py`) orchestrates a multi-stage pipeline (`detector/pipeline.py`):

1. **Frame extraction** — pull frames from video at a configurable FPS
   (`frame_extraction.py`), with a **Laplacian-variance blur filter** to drop
   useless/motion-blurred frames.
2. **Detection** — a local **YOLO** road-damage model (default: YOLOv11-x trained
   on RDD2022, the Road Damage Dataset) detects hazards and bounding boxes
   (`yolo_client.py`). A legacy **Gemini vision** detector is also selectable.
3. **Base scoring** — `scoring.py` computes a priority score + label per hazard
   from type, severity, and confidence.
4. **Deduplication** — collapse multiple frames of the same physical hazard into
   one "best frame" record (`dedupe.py`).
5. **GPS sync** — attach coordinates from a real `.gpx`/`.csv` track, or lay a
   synthetic route for map demos when footage has no GPS (`gps_sync.py`). Each
   run records a `gps_source` of `gpx` / `synthetic` / `none`.
6. **OSM enrichment** *(optional)* — reverse-geocode road name / road class /
   nearby POIs via OpenStreetMap Overpass, with a local cache
   (`osm_context.py`, `cache.py`).
7. **Street aggregation** — a persistent hazard registry
   (`street_registry.py`) does spatial dedup, counts hazards per street, and
   produces a per-street "weight" that feeds back into priority. Includes a
   spatial-bucket fallback for street naming when OSM data isn't available.
8. **AI triage (Gemini 2.5 Pro)** — `gemini_priority.py` sends the annotated
   frame + context (type, severity, street counts) to Gemini, which returns a
   **bounded priority multiplier** and **concise reasons**. This produces a
   `final_priority` (0–10) and an explainable justification list. Results are
   **checkpointed incrementally** so a long evaluation is robust to interruption.

Output is a single `detections.json` consumed by the web app.

## The government operations database
- A **FastAPI** backend (`server/`) exposes CRUD over hazard "occurrences":
  `GET / POST / PATCH / DELETE /api/occurrences`, plus `/api/reseed` to rebuild
  from the latest detections and `/api/health`.
- **Pluggable storage** (`server/store.py`): uses **Supabase Postgres** (via its
  PostgREST API) when configured, and transparently falls back to a local JSON
  store otherwise. The API contract is identical for both, so migrating is a
  pure env-var change.
- **Security choice**: the browser talks to FastAPI, and FastAPI talks to
  Supabase using a **server-side secret key** — write credentials never reach the
  client. (For production: add Supabase Auth + row-level policies.)
- Each occurrence stores an **exact location** (lat/lng) when available, a 0–10
  **score**, severity, type, road name, source (`detection` vs `manual`),
  times-seen, status, and the AI justification.

## The map + severity model
- Map markers are **colored by a 0–10 severity score**:
  - **white** for 0–4 (low)
  - **orange** for 4–7 (moderate)
  - **red** for 7–10 (high)
- **No-GPS footage shows no markers by design.** Hazards from footage without
  real GPS are stored with null coordinates and the map shows a clear empty
  state instead of fake pins — so operators are never misled about location.
- Operators can manually add a located occurrence (e.g., from a field report)
  and it immediately appears on the map with the correct color.

## Web app (frontend)
React + TypeScript + Vite + Tailwind, with three tabs (`web/`):
- **Map** — Mapbox GL view with severity-colored markers, a legend, and the
  no-location empty state.
- **Analysis Review** — frame-by-frame detection review; clickable priority
  scores reveal the Gemini reasons; per-street stats.
- **Operations DB** — the government management table: add form, delete, reseed,
  severity-colored scores, source/located indicators, and a live badge showing
  whether storage is **Supabase** or **Local JSON**.

## Tech stack
- **Detection/ML**: Ultralytics YOLO (YOLOv11-x, RDD2022 weights), PyTorch,
  Hugging Face Hub (weights), OpenCV (frames + blur filter).
- **AI triage / reasoning**: Google Gemini 2.5 Pro (`google-generativeai`).
- **Backend**: FastAPI + Uvicorn, Pydantic, Supabase (Postgres / PostgREST),
  requests, python-dotenv.
- **Geo**: gpxpy (GPS tracks), OpenStreetMap Overpass (enrichment).
- **Frontend**: React, TypeScript, Vite, TailwindCSS, Mapbox GL, Lucide icons.
- **CLI**: Click.

## Architecture (data flow)
```
footage ──> YOLO detect ──> score ──> dedupe ──> GPS sync ──> OSM enrich
                                                       │
                                          street aggregation (persistent)
                                                       │
                                       Gemini 2.5 Pro triage (multiplier+reasons)
                                                       │
                                                 detections.json
                                                       │
   ┌───────────────────────────────────────────────────┴─────────────┐
   │                          Web app (React)                          │
   │   Map (severity colors) · Analysis Review · Operations DB         │
   └───────────────────────────────┬───────────────────────────────────┘
                                    │  (Operations DB tab)
                          FastAPI backend (CRUD)
                                    │
                    Supabase Postgres  ⇄  (fallback) local JSON
```

## Key design decisions / challenges
- **YOLO over a VLM for detection.** We started with a vision-language model for
  detection but bounding boxes were imprecise and it produced false positives;
  switching to a YOLO road-damage model gave faster, tighter, free detections.
- **Hybrid pipeline: YOLO detects, Gemini triages.** Rather than choose one, we
  use YOLO for *where/what* and Gemini 2.5 Pro for *how urgent and why* — keeping
  detection cheap and adding explainable, context-aware prioritization.
- **Explainability.** Every prioritized hazard carries short natural-language
  reasons, so an operator can trust and justify the ranking.
- **Honest location handling.** No fake markers for footage without GPS — a
  deliberate UX/data-integrity decision.
- **Street-level memory.** A persistent registry means recurring damage on a
  street compounds priority, mimicking how real maintenance backlogs work.
- **Incremental checkpointing.** Long Gemini runs save progress continuously, so
  results are usable immediately and resilient to interruptions.
- **Pluggable storage with graceful fallback.** Supabase for real,
  multi-user/cloud operation; JSON for zero-setup local demos — same API.

## What's next
- Supabase Auth + role-based row-level security for true multi-agency access.
- Edit/resolve workflow and status history in the Operations DB.
- Multi-dataset / multi-vehicle ingestion and time-series of street conditions.
- Routing/export to work-order systems for dispatch.

## Quick facts for the writeup
- Default detector: **YOLOv11-x** trained on **RDD2022**.
- Triage model: **Gemini 2.5 Pro**.
- Hazard types: pothole, crack, obscured sign, faded marking, debris, other.
- Severity color bands: white 0–4, orange 4–7, red 7–10.
- Current demo dataset: **70 distinct hazards** (deduped from 77 raw detections),
  **live in Supabase** and verified end-to-end (list / add / edit / delete / reseed).
- Database: **Supabase Postgres** (table `road-problems`) with a local JSON fallback.

## Inspiration
We kept hitting potholes and seeing faded crosswalk lines on the same streets for
months — and realized cities mostly find out about hazards when a citizen
complains or a car gets damaged. Meanwhile, dashcams, delivery fleets, and buses
already drive every street, every day. The footage exists; the intelligence
doesn't. We wanted to turn that ambient footage into a living, prioritized map of
what's broken — and give the people who fix roads a tool that tells them *what to
fix first and why*.

## Demo script (for judging)
1. **Map tab** — open on the severity-colored map; explain the white/orange/red
   0–10 scale. Point out the honest empty state: this clip has **no GPS**, so we
   deliberately show **no fake markers**.
2. **Analysis Review tab** — scroll the detected hazards; click a priority score
   to reveal the **Gemini 2.5 Pro reasons** ("why this is urgent"). Mention YOLO
   found *where/what*, Gemini decided *how urgent and why*.
3. **Operations DB tab** — show the **"Supabase" badge** and the **70 live
   records**. Add a new occurrence with a real lat/lng + severity 5 → it saves to
   **Supabase in the cloud**.
4. **Back to Map** — the new occurrence shows up as a **red marker** at its exact
   location. Delete it from the DB to show full operator control.
5. Closing line: footage in → prioritized, explainable, cloud-backed hazard
   database out — usable by a real city operations team.

## How to run
```bash
# 1. Backend (operations DB API). Uses Supabase when SUPABASE_* env vars are set,
#    otherwise falls back to a local JSON store.
uvicorn server.app:app --reload --port 8000

# 2. Frontend (map + analysis + operations DB)
cd web && npm install && npm run dev   # http://localhost:5173

# 3. (Re)build the detection dataset from footage — optional, already provided:
python main.py --input <video_or_folder> --detector yolo \
  --save-frames-dir web/public/frames --dedupe --street --ai-priority \
  --output web/public/detections.json
```
The app runs locally; the database lives in **Supabase (cloud)**, so a government
operator's edits persist online while the review tooling runs on their machine.
