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

---

## Stage 5 — OSM location-context enrichment

**Goal:** turn each detection's exact `lat`/`lng` (ground truth from GPS) into
verified real-world context the reasoning model can use. The AI never guesses
location; it only consumes these facts.

### Pipeline ordering change
GPS sync (Stage 2) must run BEFORE this stage so coordinates exist. Move the
GPS step earlier in the chain; enrichment consumes `lat`/`lng`.

### New file: `detector/osm_context.py`
- `reverse_geocode(lat, lng) -> {road_name, road_class}` via Nominatim.
  - Required `User-Agent` header; respect 1 req/sec.
  - `road_class` from OSM highway tag (motorway/trunk/primary/secondary/
    residential/...). Maps to road_context: motorway/trunk -> freeway,
    primary/secondary -> arterial, residential/service -> residential.
- `nearby_pois(lat, lng, radius_m=50) -> list[POI]` via Overpass.
  - Categories: school, hospital, **kindergarten/daycare**
    (amenity=kindergarten), **crosswalk** (highway=crossing).
  - Return name + category + distance.
- `enrich(report_dict) -> report_dict`: add `road_name`, `road_class`,
  and `nearby_pois` to each detection.

### DECISION: OSM road_class OVERRIDES the LLM's road_context
The vision model only *guesses* road_context from the image. OSM road_class is
ground truth. When a detection gets a valid road_class, OVERWRITE its
`road_context` with the OSM-derived value, then RECOMPUTE the deterministic
`priority` (via scoring.compute_priority) so the baseline uses the verified
road type. Keep the original LLM guess in `road_context_vision` for reference.
Geocoding provider: Nominatim for v1 (switch to Mapbox only if rate-limited).

### Caching (correctness-safe, see notes)
- New file `detector/cache.py`: a local JSON (or SQLite) cache keyed by
  coordinates rounded to **5 decimal places (~1m)** — finer than GPS error, so
  distinct spots never merge.
- Cache applies ONLY to OSM lookups, never to vision analysis. A cache miss
  triggers a fresh fetch; a fetch failure falls back to `road_class=unknown`
  and empty POIs. A detection is NEVER skipped or dropped.
- CLI flags: `--no-cache` (bypass) and `--clear-cache`.

### Schema extension (`detector/schema.py`)
Add optional `road_name: Optional[str]`, `road_class: Optional[str]`,
`nearby_pois: list[POI] = []`. Keep all optional for backward compatibility.

### Acceptance criteria
- A real detection gets a correct street name + road_class from its coords.
- A coordinate near a school/hospital/crosswalk lists it within 50m.
- OSM failure degrades gracefully (unknown context, detection still scored).
- Re-running uses the cache (fast) and produces identical context.

### Commit
`feat: add OSM reverse-geocode + nearby-POI enrichment with safe caching`

---

## Stage 6 — AI reasoning triage (context + cost-of-delay economics)

**Goal:** a low-volume, high-reasoning pass that adjusts the deterministic
baseline using verified location context AND the project's core value:
minimizing total cost to the government via early intervention. Decision (b):
the deterministic score is the BASE; the AI applies a context multiplier +
written justification + an economic/urgency verdict.

### Model
`gemini-2.5-flash` with thinking enabled (Pro is gated on this key). Few
detections => one BATCH call over all of them is cheap and fast.

### Cost-of-delay reasoning the model must perform
Core principle: deferred maintenance compounds. The model weighs how fast THIS
defect will worsen and what delay costs, using:
- **Traffic exposure** (from road_class): freeway/arterial = high volume +
  speed => faster deterioration, emergency-repair premium, congestion cost.
  Residential = slower decay, cheaper to defer.
- **Deterioration drivers** (from the image description): standing water,
  surrounding cracking, edge raveling, depth/size => accelerants.
- **Defect-type economics**: a crack is the cheap fix-now-save-later case; a
  deep pothole is already costly. Preventive-maintenance math.
- **Safety/liability** (from nearby_pois): a known hazard in a crosswalk near
  a school/kindergarten carries injury + litigation cost if deferred.

### Grounded cost model (DECISION B: no hallucinated dollars)
New file `detector/cost_model.py` with CONFIGURABLE, clearly-labeled illustrative
estimates (not authoritative):
- `repair_now_cost(type, severity)` and a `deferred_cost(type, severity, road_class)`
  that applies a deterioration multiplier (higher for freeway/arterial, for
  potholes, and when water/cracking present).
- `estimated_savings = deferred_cost - repair_now_cost`.
The AI references these numbers; it must NOT invent its own figures.

### New file: `detector/triage.py`
- Input: all detections incl. type/severity/description/`lat`/`lng`/
  `road_name`/`road_class`/`nearby_pois`/deterministic `priority` + the
  cost-model figures.
- The model receives location/context/costs as FACTS (never infers them).
- Output per detection:
  - `priority_multiplier` (0.5–2.0) and `final_priority`
    (= deterministic priority * multiplier)
  - `deterioration_risk` (low | medium | high)
  - `recommended_action` (fix_now | schedule_30d | monitor)
  - `justification` (1–2 sentences citing context + economics, e.g. "Pothole on
    a freeway with standing water will expand quickly under high-speed traffic;
    fixing now (~$X) avoids a likely ~$Y emergency dig-out.")
- Deterministic score is the fallback if the triage call fails (demo-safe).

### Schema extension
Add optional `priority_multiplier`, `final_priority`, `deterioration_risk`,
`recommended_action`, `justification`, `repair_now_cost`, `deferred_cost`,
`estimated_savings` (all Optional). Map UI sorts by `final_priority` when
present, else `priority`.

### Acceptance criteria
- Hazards in sensitive contexts (crosswalk/school) rank above identical
  hazards on empty roads.
- A freeway pothole with water ranks/urges higher than an identical
  residential one, with cost-of-delay reasoning citing the cost-model figures.
- Every detection has a justification + recommended_action + savings estimate.
- Triage failure falls back cleanly to deterministic scores.

### Commit
`feat: add context + cost-of-delay AI reasoning triage`

---

## Stage 7 — Analysis Review screen (see the AI judgement + evidence)

**Goal:** a dedicated page that shows the actual analyzed image alongside the
AI's detection + reasoning, so users (and judges) can audit the AI's work.

### Dependency: persist analyzed frames
The pipeline currently discards extracted frames. Add an option to SAVE each
analyzed frame to `web/public/frames/<frame_name>` and store an `image_url`
(e.g. `/frames/frame_00007.jpg`) on each detection so the UI can display it.

### Route
Add a second page/route to the existing `web/` app (e.g. `/analysis`), with
nav between the Map and the Analysis Review.

### Layout
- A scrollable list/grid of analyzed frames. For each frame card:
  - The image itself.
  - Overlaid or listed detections with `type`, `severity`, `confidence`.
  - The exact location: `road_name`, `lat`/`lng`, nearby POIs.
  - The deterministic priority, the AI `priority_multiplier`, `final_priority`,
    `priority_label`, and the AI `justification` text.
- A detail view when a card is clicked (larger image + full reasoning).
- Filters by `priority_label` and `type`; "no issues" frames clearly marked.

### Acceptance criteria
- The page lists analyzed frames with their images loaded from
  `web/public/frames/`.
- Each detection shows image + detection + location + AI justification together.
- Works against the same `web/public/detections.json` the map uses.

### Commit
`feat: add Analysis Review page showing AI judgement with image evidence`
