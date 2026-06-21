# Implementation Plan

Shared spec between the planning chat and the coding chat. Build stages in
order. Each stage lists files, exact behavior, and acceptance criteria.
Do not change `detector/schema.py` fields that already exist; only extend.

---

## Context (already built — Stage 1)

`detector/` contains a working detection engine. `main.py` runs:
`python main.py --input <video|folder> [--mock] --output detections.json`

Output JSON shape (per detection): `frame`, `timestamp_offset_sec`, `type`,
`description`, `severity`, `confidence`, `road_context`, `priority`,
`priority_label`. The report wraps these with `source`, `generated_at`,
`frame_count`, `detections[]`.

---

## Stage 2 — GPS sync module  (build this first)

**Goal:** attach real-world coordinates to each detection by joining its
`timestamp_offset_sec` to a GPS track, so the map can place pins.

### New dependency
Add `gpxpy==1.6.2` to `requirements.txt`.

### New file: `detector/gps_sync.py`

Implement:

1. `@dataclass TrackPoint` with `time_offset_sec: float`, `lat: float`,
   `lng: float`.

2. `load_track(path: str) -> list[TrackPoint]`
   - Supports `.gpx` (parse with gpxpy) and `.csv` (columns:
     `timestamp,lat,lng` where timestamp is ISO8601 or epoch seconds).
   - Normalize all points to **seconds elapsed from the first point**
     (`time_offset_sec`), sorted ascending. This makes the track align to the
     video timeline, which also starts at 0.

3. `interpolate(track: list[TrackPoint], t: float) -> tuple[float, float]`
   - Linear interpolation of lat/lng at elapsed time `t`.
   - If `t` is before the first or after the last point, clamp to the nearest
     endpoint. Raise `ValueError` if track is empty.

4. `apply_gps(report_dict: dict, track: list[TrackPoint], time_offset: float = 0.0) -> dict`
   - For each detection, compute `t = timestamp_offset_sec + time_offset`,
     interpolate, and add `lat` and `lng` keys to the detection dict.
   - Return the mutated report dict.

5. `generate_mock_track(num_points: int = 120, start_lat: float = 37.8716, start_lng: float = -122.2727, spacing_sec: float = 1.0) -> list[TrackPoint]`
   - Synthetic route near UC Berkeley for `--mock` runs. Walk lat/lng in small
     steps (~0.0003 deg per point) to simulate a driving loop.

### Schema extension
In `detector/schema.py`, add optional `lat: float | None = None` and
`lng: float | None = None` to the `Detection` model. Keep them optional so
Stage 1 output is still valid.

### CLI wiring (`main.py`)
Add options:
- `--gpx PATH` : GPS track file (.gpx or .csv). Optional.
- `--time-offset FLOAT` (default 0.0): seconds to shift video time to match
  GPS clock (camera/GPS clock drift correction).

Behavior:
- If `--gpx` given, load the track and call `apply_gps` after scoring,
  before writing JSON.
- If `--mock` and no `--gpx`, use `generate_mock_track` so mock runs still
  produce coordinates (so the map has data).

### Acceptance criteria
- `python main.py --input ./samples --mock` produces detections that now
  include `lat`/`lng` near Berkeley.
- A real run with `--gpx track.gpx` places detections along the track.
- Out-of-range timestamps clamp instead of crashing.
- Mock run still passes (rule: pipeline always runs in mock mode).

### Commit
`feat: add GPS sync module (GPX/CSV track join + interpolation)`

---

## Stage 3 — Map UI (React + Mapbox)

**Goal:** a polished web app that loads the enriched `detections.json` and
shows a priority map + ranked work-order list. This is the demo centerpiece.

### Stack
- Vite + React + TypeScript
- TailwindCSS
- `react-map-gl` + `mapbox-gl`
- `lucide-react` icons
- `recharts` for the stats panel
- Place under `web/` (separate from the Python package).

### Env
- `VITE_MAPBOX_TOKEN` in `web/.env` (add `web/.env.example`). Never commit the
  real token.

### Data
- For the hackathon, copy `detections.json` into `web/public/detections.json`
  and fetch it at runtime. (Later this can be a backend endpoint.)

### Features
1. **Map** (full-screen):
   - Color-coded markers by `priority_label`:
     CRITICAL=red, HIGH=orange, MEDIUM=yellow, LOW=gray.
   - Optional heatmap layer weighted by `priority` (toggle button).
   - Click a marker -> popup with `type`, `description`, `severity`,
     `priority`, `priority_label`, and the frame name.
2. **Sidebar work-order list**:
   - Detections sorted by `priority` desc.
   - Each row: priority badge, type, road_context, description.
   - Clicking a row flies the map to that marker.
   - Filter by `priority_label` and by `type`.
3. **Stats panel** (small dashboard):
   - Counts by type (bar chart) and by priority_label (donut/bar).
   - Total detections + count of CRITICAL/HIGH.
4. **Polish**: clean municipal-dashboard aesthetic, loading state, empty state.

### Acceptance criteria
- `npm install && npm run dev` in `web/` boots the app.
- With the mock `detections.json` (Berkeley coords), markers render on the map
  and the list/stats populate.
- Clicking list rows and markers stays in sync.

### Commit
`feat: add React + Mapbox map UI for priority visualization`

---

## Stage 4 — (optional) spatial clustering
Group detections within ~25m so dense problem zones (e.g. a freeway stretch of
potholes) surface as a single high-priority cluster. Add a `cluster_id` and an
aggregate cluster priority. Only do this after Stages 2 and 3 work.
