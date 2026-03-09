# 🚦 CityFlow — Traffic Intelligence System

Full-stack congestion tracking system: **FastAPI + Supabase + OpenAI GPT-4o-mini + pure HTML/JS dashboard**.

---

## Project Structure

```
├── main.py                    ← FastAPI backend (all API routes)
├── requirements.txt
├── .env.example               ← Copy to .env and fill in keys (do not commit .env)
├── templates/
│   └── dashboard.html         ← Single-file dashboard (required)
├── scripts/
│   └── generate_data.py       ← Synthetic data generator
├── sql/
│   └── schema.sql             ← Run once in Supabase SQL Editor
├── static/                    ← Optional static assets
├── check_supabase.py          ← Optional: verify Supabase connection
└── README.md
```

---

## Quick Start (4 steps)

### Step 1 — Supabase Setup

1. Go to [supabase.com](https://supabase.com) → New project
2. Open **SQL Editor** → paste contents of `sql/schema.sql` → **Run**
3. Go to **Settings → API** → copy:
   - Project URL
   - `service_role` secret key (not the anon key)

### Step 2 — Configure environment

```bash
cp .env.example .env
# Edit .env with your Supabase URL, service key, and OpenAI key
```

### Step 3 — Generate synthetic data

```bash
pip install supabase python-dotenv
python scripts/generate_data.py
# Inserts 20 locations × 7 days × 15-min intervals ≈ 13,400 readings
```

### Step 4 — Start the server

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Open http://localhost:8000
```

The interactive API docs are at **http://localhost:8000/docs**

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/congestion/current` | Latest reading per location |
| GET | `/api/congestion/history` | Time-series (location, zone, hours) |
| GET | `/api/congestion/top` | Top N most congested right now |
| GET | `/api/congestion/summary` | 7-day hourly aggregates |
| GET | `/api/accidents/current` | Recent accident reports (zone, days, limit) |
| GET | `/api/accidents/history` | Historical accidents (zone, location_id, days, severity) |
| GET | `/api/osm/ways` | OSM road geometry in bbox (optional, for map) |
| POST | `/api/ai/summary` | GPT-4o-mini narrative summary |

### Query Examples

```bash
# Critical spots in Midtown
GET /api/congestion/current?zone=Midtown&severity=critical

# Brooklyn history, last 2 days
GET /api/congestion/history?zone=Brooklyn&hours=48

# Top 5 worst right now
GET /api/congestion/top?limit=5

# 2-week hourly pattern for Queens
GET /api/congestion/summary?zone=Queens&days=14

# AI: Is today better or worse than usual?
POST /api/ai/summary
{"query_type": "comparison"}
```

---

## Database Schema

### `locations`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| name | text | Road/intersection name |
| zone | text | Midtown / Downtown / Uptown / Brooklyn / Queens |
| lat, lng | float | Coordinates |
| road_type | text | intersection / segment / highway |

### `congestion_readings`
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| location_id | uuid | FK → locations |
| timestamp | timestamptz | Reading time |
| congestion_level | int | **0–100** (core metric) |
| speed_mph | float | Observed speed |
| delay_minutes | float | Delay vs free-flow |
| volume | int | Vehicles/hour |

### Severity Scale
| Range | Label | Color |
|-------|-------|-------|
| 0–29 | LOW | 🟢 Green |
| 30–54 | MODERATE | 🟡 Yellow |
| 55–74 | HIGH | 🟠 Orange |
| 75–100 | CRITICAL | 🔴 Red |

---

## Dashboard Features

| Tab | What you see |
|-----|-------------|
| **Overview** | 4 KPI cards, live traffic map (circle markers), location table, Top-5 list, 7-day sparkline; per-point “View real-time monitoring” (24h chart + live video placeholder) |
| **Trends** | 24-hour area chart, AM/Midday/PM peak summary cards |
| **Accidents** | Recent and historical accident tables with zone/severity filters |
| **AI Insights** | 4 query modes (Worst Now / 7-Day Trend / vs Typical / Custom), GPT-4o-mini analysis |
| **API Docs** | Full endpoint reference with parameters and example requests |

Auto-refreshes every 60 seconds.

---

## Synthetic Data Patterns

- **20 NYC-inspired locations** across 5 zones
- **Weekday peaks**: AM rush 7–9am (~95 level), PM rush 5–7pm (~96 level)
- **Weekend**: Mild midday curve, no sharp peaks
- **Zone variation**: Midtown baseline ~72, Queens ~46
- **Gaussian noise**: ±7% for natural-looking variation

---

## Pipeline Architecture (Lab Requirement)

The system follows the required pipeline:

```
Supabase (PostgreSQL) → REST API (FastAPI) → Dashboard (web app) → AI (OpenAI)
```

- **Database**: Supabase hosts `locations`, `congestion_readings`, `accidents`; dashboard and API read/write via service key.
- **API**: FastAPI serves JSON endpoints for congestion, accidents, and AI summary; same process serves the dashboard UI.
- **Dashboard**: Single-page web app (HTML/JS) delivered at `/`; provides KPIs, maps, charts, and AI insights. (Task allows “Shiny in R or in Python”; this is the Python option—a web app that delivers results to the user.)
- **AI**: `POST /api/ai/summary` pulls a data snapshot from the DB and sends it to GPT-4o-mini for plain-language traffic summaries.

---

## Test Executions (2–3 Demonstrations)

**Prerequisites:** Server running (`uvicorn main:app --port 8000`), `.env` with valid Supabase and OpenAI keys, and sample data loaded (`python scripts/generate_data.py`).

### Test 1 — API: Current congestion (database → API)

```bash
curl -s "http://localhost:8000/api/congestion/current?limit=3" | python -m json.tool
```

**Expected:** JSON with `count`, `timestamp`, and `data` array of up to 3 locations; each object has `name`, `zone`, `congestion_level`, `speed_mph`, `delay_minutes`. Proves Supabase is connected and the API returns DB data.

### Test 2 — API: AI summary (database → API → AI)

```bash
curl -s -X POST "http://localhost:8000/api/ai/summary" \
  -H "Content-Type: application/json" \
  -d '{"query_type": "comparison"}' | python -m json.tool
```

**Expected:** JSON with `summary` (plain-language text from GPT-4o-mini), `data_snapshot` (e.g. `city_avg_now`, `typical_this_hour`, `delta`), and `generated_at`. Proves the AI uses DB data to produce insights.

### Test 3 — Full pipeline (dashboard + API + DB)

1. Open `http://localhost:8000/` in a browser.
2. Confirm Overview tab shows KPI cards, location table, and map with circle markers.
3. Click a map marker → “VIEW REAL-TIME MONITORING” → modal shows 24h congestion chart and optional live video placeholder.
4. Open **AI Insights** tab → choose “Compare to typical” → **Generate** → confirm a short narrative appears.

**Expected:** Dashboard loads, data appears from the API, and AI summary is displayed. Proves database → API → dashboard → AI flow.

---

## Codebook — Pipeline Files and Variables

| File | Purpose | Key variables / usage |
|------|---------|------------------------|
| `main.py` | FastAPI app: serves dashboard, REST API, and AI summary. | `_get_supabase()`, `_get_openai()` — lazy DB/OpenAI clients. Endpoints: `/api/congestion/*`, `/api/accidents/*`, `/api/ai/summary`. |
| `templates/dashboard.html` | Single-page dashboard UI. | `currentData`, `hourlyData` — state from API. `renderTrafficMap()`, `renderAccidentsCurrent()` — render map and tables. Calls `API` (base URL) for all requests. |
| `scripts/generate_data.py` | Seeds Supabase (or writes seed JSON). | `RAW_LOCATIONS` — 20 locations. `ZONE_BASE`, `_WEEKDAY`/`_WEEKEND` — congestion patterns. Writes `locations`, `congestion_readings`, `accidents`. |
| `sql/schema.sql` | Supabase schema. | Tables: `locations` (id, name, zone, lat, lng, road_type), `congestion_readings` (location_id, timestamp, congestion_level, speed_mph, delay_minutes, volume), `accidents` (location_id, occurred_at, severity, description, vehicles_involved, injuries). View: `latest_congestion`. |
| `locations_seed.json` | Optional seed data. | Array of location objects; used if Supabase is not configured or for manual import. |
| `readings_seed.json` | Optional seed data. | Array of congestion reading objects (location_id, timestamp, congestion_level, etc.). |
| `accidents_seed.json` | Optional seed data. | Array of accident records (location_id, occurred_at, severity, description, etc.). |
| `.env` | Local config (not committed). | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY` — required for full pipeline. |

**Data variables (API/DB):** `congestion_level` (0–100); `timestamp` / `occurred_at` (ISO 8601); `zone` (e.g. Midtown, Brooklyn); `severity` for accidents (minor, moderate, serious, fatal).

---

## Deployment (DigitalOcean or Posit Connect)

- **DigitalOcean:** Run the app as a Web Process (e.g. `uvicorn main:app --host 0.0.0.0 --port $PORT`). Add Supabase and OpenAI env vars in the DO app dashboard. Use a static buildpack or Dockerfile that installs `requirements.txt` and runs the above command.
- **Posit Connect:** Publish as a Python API (FastAPI) or document the run command so Connect can execute `uvicorn main:app` with the same env vars.
- After deployment, use the deployed base URL in the test executions above (replace `http://localhost:8000` with your deployed URL). Ensure the dashboard at `/` and `/docs` are accessible.

---

## Lab Compliance Checklist

| Requirement | Status |
|-------------|--------|
| **Tool implementation** | |
| Supabase database in pipeline | Yes — schema in `sql/schema.sql`, all data via Supabase client in `main.py`. |
| REST API for data processing | Yes — FastAPI in `main.py`; `/api/congestion/*`, `/api/accidents/*`, `/api/ai/summary`. |
| Query AI model for prompt problem | Yes — `POST /api/ai/summary` sends DB snapshot to GPT-4o-mini. |
| Serve app to deliver results to user | Yes — Dashboard at `/` (HTML/JS web app; Python stack). |
| Effective, working tool | Yes when `.env` and data are configured; run locally or deploy. |
| **Tool design** | |
| Pipeline: DB → API → dashboard → AI | Yes — see Pipeline Architecture above. |
| Clear user and use case | Yes — city traffic analysts viewing congestion and AI summaries. |
| Minimal reasonable user inputs | Yes — zone/date filters and one-click AI query types. |
| **Documentation** | |
| 2–3 accurate test executions | Yes — see Test Executions above. |
| Clear demonstration with tests | Yes — each test has expected outcome. |
| Documentation of functions/inputs | Yes — README, API table, codebook, and `/docs`. |
| Codebook + README for pipeline | Yes — Codebook section and this README. |
| Reproducible code, public GitHub | Your responsibility — push repo and add GitHub URL here. |

If your course provided **MIDTERM_DL_challenge_prompts.md**, align the problem statement and deliverables with that prompt (e.g. add a one-line “This solves the midterm prompt by …” in the README).
