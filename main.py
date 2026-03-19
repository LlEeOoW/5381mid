"""
main.py  —  CityFlow FastAPI backend
──────────────────────────────────────
Run:  uvicorn main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

# Base directory of this file (so paths work when CWD is not project root, e.g. on DigitalOcean)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
from supabase import create_client, Client

load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)

# ── Clients (lazy init so server starts without valid keys) ───────────────────
_supabase: Optional[Client] = None
_openai_client: Optional[OpenAI] = None
REQUIRED_ENV_VARS = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY")

def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        if not url or not key or url.startswith("https://YOUR"):
            raise HTTPException(503, "Configure SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        if key.startswith("sb_publishable_"):
            raise HTTPException(
                503,
                "SUPABASE_SERVICE_KEY is a publishable key; use service_role/secret key for backend.",
            )
        _supabase = create_client(url, key)
    return _supabase

def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key or api_key.startswith("sk-YOUR"):
            raise HTTPException(503, "Configure OPENAI_API_KEY in .env")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

def _config_status() -> dict:
    missing = []
    placeholders = []
    invalid_types = []
    values = {
        "SUPABASE_URL": os.environ.get("SUPABASE_URL", "").strip(),
        "SUPABASE_SERVICE_KEY": os.environ.get("SUPABASE_SERVICE_KEY", "").strip(),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "").strip(),
    }
    placeholder_prefix = {
        "SUPABASE_URL": "https://YOUR",
        "SUPABASE_SERVICE_KEY": "YOUR_",
        "OPENAI_API_KEY": "sk-YOUR",
    }

    for key in REQUIRED_ENV_VARS:
        value = values.get(key, "")
        if not value:
            missing.append(key)
        elif value.startswith(placeholder_prefix[key]):
            placeholders.append(key)
    if values["SUPABASE_SERVICE_KEY"].startswith("sb_publishable_"):
        invalid_types.append("SUPABASE_SERVICE_KEY (publishable key is for frontend only)")

    return {
        "ok": not missing and not placeholders and not invalid_types,
        "missing": missing,
        "placeholder_values": placeholders,
        "invalid_types": invalid_types,
    }

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CityFlow Traffic Intelligence API",
    description="Real-time & historical congestion data for city transportation authorities.",
    version="1.0.0",
    docs_url="/docs",
)

@app.on_event("startup")
async def startup_config_check():
    status = _config_status()
    if status["ok"]:
        print("Startup check: required environment variables are configured.")
        return
    print("Startup check warning: environment configuration is incomplete.")
    if status["missing"]:
        print(f"Missing vars: {', '.join(status['missing'])}")
    if status["placeholder_values"]:
        print(f"Placeholder vars: {', '.join(status['placeholder_values'])}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ── Helpers ────────────────────────────────────────────────────────────────
SEVERITY_MAP = {"low": (0, 29), "moderate": (30, 54), "high": (55, 74), "critical": (75, 100)}

def _since(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

def _since_days(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

# ══════════════════════════════════════════════════════════════════════
# SERVE DASHBOARD
# ══════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard():
    path = os.path.join(BASE_DIR, "templates", "dashboard.html")
    with open(path, encoding="utf-8") as f:
        return f.read()

@app.get(
    "/health",
    summary="Service health and configuration status",
    tags=["System"],
)
async def health():
    status = _config_status()
    return {
        "status": "ok" if status["ok"] else "degraded",
        "service": "cityflow-api",
        "config": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# ══════════════════════════════════════════════════════════════════════
# GET /api/osm/ways — proxy for Overpass API (real road geometry for map)
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/osm/ways",
    summary="OSM highway ways in bbox (for congestion map)",
    tags=["Map"],
)
async def get_osm_ways(
    min_lat: float = Query(..., description="South"),
    max_lat: float = Query(..., description="North"),
    min_lng: float = Query(..., description="West"),
    max_lng: float = Query(..., description="East"),
):
    """Fetches OpenStreetMap highway ways in the given bbox; used to color real roads by congestion."""
    bbox = f"{min_lat},{min_lng},{max_lat},{max_lng}"
    query = f'[out:json][timeout:30][bbox:{bbox}];way["highway"];out geom;'
    servers = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    last_err = None
    async with httpx.AsyncClient(timeout=35.0) as client:
        for url in servers:
            try:
                r = await client.get(url, params={"data": query})
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                continue
    raise HTTPException(502, f"Overpass unavailable: {last_err}")


# ══════════════════════════════════════════════════════════════════════
# GET /api/congestion/current
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/congestion/current",
    summary="Latest reading per location",
    tags=["Congestion"],
)
async def get_current(
    zone: Optional[str] = Query(None, description="Filter by zone name, e.g. Midtown"),
    severity: Optional[str] = Query(None, description="low | moderate | high | critical"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Returns the **most recent** congestion reading for every monitored location.
    Optionally filter by zone or severity level.
    """
    try:
        q = _get_supabase().table("latest_congestion").select("*").order(
            "congestion_level", desc=True
        ).limit(limit)

        if zone:
            q = q.eq("zone", zone)
        if severity:
            lo, hi = SEVERITY_MAP.get(severity, (0, 100))
            q = q.gte("congestion_level", lo).lte("congestion_level", hi)

        res = q.execute()
        return {"count": len(res.data), "timestamp": datetime.now(timezone.utc).isoformat(), "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Supabase error: {str(e)}")

# ══════════════════════════════════════════════════════════════════════
# GET /api/congestion/history
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/congestion/history",
    summary="Time-series readings",
    tags=["Congestion"],
)
async def get_history(
    location_id: Optional[str] = Query(None, description="UUID of a specific location"),
    zone: Optional[str] = Query(None, description="Filter by zone"),
    hours: int = Query(24, ge=1, le=168, description="Lookback window (max 168 = 7 days)"),
):
    """
    Returns time-ordered congestion readings.
    Use `location_id` for a single road or `zone` for an area.
    """
    q = (
        _get_supabase().table("congestion_readings")
        .select("id, location_id, timestamp, congestion_level, speed_mph, delay_minutes, volume, locations(name, zone, road_type)")
        .gte("timestamp", _since(hours))
        .order("timestamp", desc=False)
        .limit(5000)
    )
    if location_id:
        q = q.eq("location_id", location_id)

    res = q.execute()
    data = res.data

    # Filter by zone after join (Supabase REST doesn't support nested eq easily)
    if zone:
        data = [r for r in data if r.get("locations", {}).get("zone") == zone]

    return {"count": len(data), "hours_requested": hours, "since": _since(hours), "data": data}

# ══════════════════════════════════════════════════════════════════════
# GET /api/congestion/top
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/congestion/top",
    summary="Most congested locations right now",
    tags=["Congestion"],
)
async def get_top(
    limit: int = Query(10, ge=1, le=20),
    zone: Optional[str] = Query(None),
):
    """Returns the N most congested locations based on latest readings."""
    q = _get_supabase().table("latest_congestion").select("*").order("congestion_level", desc=True).limit(limit)
    if zone:
        q = q.eq("zone", zone)
    res = q.execute()
    return {"count": len(res.data), "timestamp": datetime.now(timezone.utc).isoformat(), "data": res.data}

# ══════════════════════════════════════════════════════════════════════
# GET /api/congestion/summary
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/congestion/summary",
    summary="Aggregated statistics (hourly breakdown)",
    tags=["Congestion"],
)
async def get_summary(
    zone: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=30),
):
    """
    Returns 24-hour average congestion breakdown plus key stats.
    Great for understanding typical daily patterns.
    """
    q = (
        _get_supabase().table("congestion_readings")
        .select("timestamp, congestion_level, locations!inner(zone)")
        .gte("timestamp", _since_days(days))
        .limit(10000)
    )
    if zone:
        q = q.eq("locations.zone", zone)

    res = q.execute()
    data = res.data
    if not data:
        raise HTTPException(404, "No data found for the given parameters.")

    by_hour: dict[int, list[int]] = {h: [] for h in range(24)}
    total = 0
    mn, mx = 101, -1
    for r in data:
        h = datetime.fromisoformat(r["timestamp"]).hour
        lv = r["congestion_level"]
        by_hour[h].append(lv)
        total += lv
        mn = min(mn, lv)
        mx = max(mx, lv)

    hourly = [
        {"hour": h, "avg_congestion": round(sum(v) / len(v)) if v else 0, "sample_count": len(v)}
        for h, v in by_hour.items()
    ]
    peak = max(hourly, key=lambda x: x["avg_congestion"])

    return {
        "zone": zone or "All Zones",
        "days_analyzed": days,
        "total_readings": len(data),
        "avg_congestion": round(total / len(data)),
        "min_congestion": mn,
        "max_congestion": mx,
        "peak_hour": peak["hour"],
        "peak_hour_avg": peak["avg_congestion"],
        "hourly_breakdown": hourly,
    }

# ══════════════════════════════════════════════════════════════════════
# GET /api/accidents/current — recent accidents (e.g. last 7 days)
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/accidents/current",
    summary="Recent accidents (latest first)",
    tags=["Accidents"],
)
async def get_accidents_current(
    zone: Optional[str] = Query(None, description="Filter by zone"),
    days: int = Query(7, ge=1, le=30, description="Lookback days"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Returns recent accident/crash reports, optionally filtered by zone.
    Joins with locations for name and zone.
    """
    since = _since_days(days)
    q = (
        _get_supabase().table("accidents")
        .select("id, location_id, occurred_at, severity, description, vehicles_involved, injuries, locations(name, zone)")
        .gte("occurred_at", since)
        .order("occurred_at", desc=True)
        .limit(limit)
    )
    res = q.execute()
    data = res.data or []

    if zone:
        data = [r for r in data if r.get("locations") and r["locations"].get("zone") == zone]

    # Flatten location name/zone for convenience (location_id can be null)
    for r in data:
        loc = r.pop("locations", None) or {}
        r["location_name"] = loc.get("name") or "—"
        r["zone"] = loc.get("zone") or "—"

    return {
        "count": len(data),
        "days_requested": days,
        "since": since,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


# ══════════════════════════════════════════════════════════════════════
# GET /api/accidents/history — historical accidents with filters
# ══════════════════════════════════════════════════════════════════════

@app.get(
    "/api/accidents/history",
    summary="Historical accident records",
    tags=["Accidents"],
)
async def get_accidents_history(
    zone: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None, description="Filter by location UUID"),
    days: int = Query(30, ge=1, le=365),
    severity: Optional[str] = Query(None, description="minor | moderate | serious | fatal"),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Returns accident records over a time window with optional zone, location, and severity filters.
    """
    since = _since_days(days)
    q = (
        _get_supabase().table("accidents")
        .select("id, location_id, occurred_at, severity, description, vehicles_involved, injuries, locations(name, zone)")
        .gte("occurred_at", since)
        .order("occurred_at", desc=True)
        .limit(limit)
    )
    if location_id:
        q = q.eq("location_id", location_id)
    if severity:
        q = q.eq("severity", severity)

    res = q.execute()
    data = res.data or []

    if zone:
        data = [r for r in data if r.get("locations") and r["locations"].get("zone") == zone]

    for r in data:
        loc = r.pop("locations", None) or {}
        r["location_name"] = loc.get("name") or "—"
        r["zone"] = loc.get("zone") or "—"

    return {
        "count": len(data),
        "days_requested": days,
        "since": since,
        "data": data,
    }


# ══════════════════════════════════════════════════════════════════════
# POST /api/ai/summary
# ══════════════════════════════════════════════════════════════════════

class AISummaryRequest(BaseModel):
    query_type: str = "current"   # current | trend | comparison | custom
    custom_prompt: Optional[str] = None

@app.post(
    "/api/ai/summary",
    summary="AI-generated plain-language traffic summary",
    tags=["AI"],
)
async def ai_summary(body: AISummaryRequest):
    """
    Fetches a compact data snapshot from Supabase, sends it to GPT-4o-mini,
    and returns a short actionable narrative for transportation analysts.
    """
    now = datetime.now(timezone.utc)

    # ── Pull compact data snapshot ─────────────────────────────────────
    top_res = _get_supabase().table("latest_congestion").select(
        "name, zone, congestion_level, speed_mph, delay_minutes"
    ).order("congestion_level", desc=True).limit(10).execute()
    top_now = top_res.data or []

    avg_now = round(sum(r["congestion_level"] for r in top_now) / len(top_now)) if top_now else 0

    # 7-day hourly pattern
    hist_res = (
        _get_supabase().table("congestion_readings")
        .select("timestamp, congestion_level")
        .gte("timestamp", _since_days(7))
        .limit(6000)
        .execute()
    )
    by_hour: dict[int, list[int]] = {h: [] for h in range(24)}
    for r in (hist_res.data or []):
        h = datetime.fromisoformat(r["timestamp"]).hour
        by_hour[h].append(r["congestion_level"])

    hourly_avg = [
        {"hour": h, "avg": round(sum(v) / len(v)) if v else 0}
        for h, v in by_hour.items()
    ]
    typical_now = next((x["avg"] for x in hourly_avg if x["hour"] == now.hour), 0)
    delta = avg_now - typical_now

    # Zone summary
    zone_map: dict[str, list[int]] = {}
    for r in top_now:
        zone_map.setdefault(r["zone"], []).append(r["congestion_level"])
    zone_summary = [
        {"zone": z, "avg": round(sum(v) / len(v))} for z, v in zone_map.items()
    ]

    data_payload = {
        "current_time": now.strftime("%Y-%m-%d %H:%M UTC"),
        "city_avg_congestion_now": avg_now,
        "typical_congestion_this_hour_7d_avg": typical_now,
        "delta_vs_typical": delta,
        "top_10_congested_locations": top_now,
        "zone_breakdown": zone_summary,
        "hourly_7day_pattern": hourly_avg,
    }

    prompts = {
        "current": (
            "Which areas are most congested right now? "
            "Name specific roads and give actionable advice on what to avoid."
        ),
        "trend": (
            "Based on 7-day historical patterns, summarize how congestion varies by time of day. "
            "When are the best and worst times to travel?"
        ),
        "comparison": (
            "Compare current congestion to the typical level for this hour. "
            "Is today better, worse, or about normal? Quantify the difference."
        ),
        "custom": body.custom_prompt or "Provide a general congestion summary.",
    }
    user_prompt = prompts.get(body.query_type, prompts["current"])
    user_prompt += f"\n\nData: {data_payload}"

    completion = _get_openai().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a traffic intelligence analyst for a city transportation authority. "
                    "Produce SHORT, SPECIFIC, ACTIONABLE summaries (3-5 sentences or a tight bullet list). "
                    "Always name roads, quote numbers, and give concrete takeaways. No filler words."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.35,
        max_tokens=350,
    )

    return {
        "query_type": body.query_type,
        "summary": completion.choices[0].message.content,
        "data_snapshot": {
            "city_avg_now": avg_now,
            "typical_this_hour": typical_now,
            "delta": delta,
            "worst_location": top_now[0]["name"] if top_now else "N/A",
        },
        "generated_at": now.isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
