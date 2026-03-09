"""
scripts/generate_data.py
────────────────────────
Generates ~13 000+ realistic congestion records for 20 NYC-inspired locations
over the past 7 days (one reading every 15 minutes per location).

Usage
-----
  pip install supabase python-dotenv
  python scripts/generate_data.py

If Supabase credentials are not set the data is saved to
  scripts/locations_seed.json
  scripts/readings_seed.json
so you can import them manually via Supabase's Table Editor.
"""

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# ── Try to load Supabase ───────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    from supabase import create_client
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    _url  = os.getenv("SUPABASE_URL")
    _key  = os.getenv("SUPABASE_SERVICE_KEY")
    USE_SUPABASE = bool(_url and _key and not _url.startswith("https://YOUR"))
except ImportError:
    USE_SUPABASE = False

# ── 20 NYC-inspired locations ──────────────────────────────────────────────
RAW_LOCATIONS = [
    # Midtown
    ("5th Ave & 42nd St",         "Midtown",   40.7527, -73.9820, "intersection"),
    ("7th Ave & 34th St",          "Midtown",   40.7484, -73.9967, "intersection"),
    ("Park Ave Tunnel North",      "Midtown",   40.7549, -73.9741, "segment"),
    ("Lincoln Tunnel Approach",    "Midtown",   40.7587, -74.0020, "highway"),
    ("9th Ave & 57th St",          "Midtown",   40.7668, -73.9928, "intersection"),
    # Downtown
    ("FDR Drive at 23rd St",       "Downtown",  40.7396, -73.9737, "highway"),
    ("Canal St & Broadway",        "Downtown",  40.7186, -74.0020, "intersection"),
    ("Brooklyn Bridge Entrance",   "Downtown",  40.7061, -73.9969, "segment"),
    ("West Side Hwy at Chambers",  "Downtown",  40.7150, -74.0133, "highway"),
    ("Wall St & Broadway",         "Downtown",  40.7074, -74.0113, "intersection"),
    # Uptown
    ("125th St & Lex Ave",         "Uptown",    40.7960, -73.9373, "intersection"),
    ("FDR Drive at 96th St",       "Uptown",    40.7850, -73.9453, "highway"),
    ("Broadway & 145th St",        "Uptown",    40.8237, -73.9413, "intersection"),
    ("Riverside Dr & 72nd St",     "Uptown",    40.7777, -73.9880, "segment"),
    # Brooklyn
    ("Atlantic Ave & Flatbush",    "Brooklyn",  40.6843, -73.9774, "intersection"),
    ("BQE at Atlantic Ave",        "Brooklyn",  40.6880, -73.9900, "highway"),
    ("4th Ave & 9th St",           "Brooklyn",  40.6707, -73.9867, "intersection"),
    # Queens
    ("Queens Blvd & Junction",     "Queens",    40.7282, -73.8672, "segment"),
    ("LIE at Grand Ave",           "Queens",    40.7204, -73.8656, "highway"),
    ("Northern Blvd & Main St",    "Queens",    40.7592, -73.8303, "intersection"),
]

# Base congestion by zone (0-100 scale)
ZONE_BASE = {"Midtown": 72, "Downtown": 63, "Uptown": 48, "Brooklyn": 54, "Queens": 46}
ROAD_MULT = {"intersection": 1.10, "segment": 1.00, "highway": 0.88}

# Hourly traffic shape (index = hour 0-23)
_WEEKDAY = [
    0.14, 0.09, 0.07, 0.07, 0.11, 0.24,   # 0-5
    0.54, 0.83, 0.96, 0.74, 0.59, 0.57,   # 6-11
    0.61, 0.57, 0.59, 0.71, 0.89, 0.96,   # 12-17
    0.84, 0.69, 0.54, 0.41, 0.29, 0.19,   # 18-23
]
_WEEKEND = [
    0.19, 0.14, 0.10, 0.09, 0.11, 0.17,
    0.24, 0.30, 0.40, 0.50, 0.60, 0.69,
    0.74, 0.71, 0.67, 0.64, 0.69, 0.71,
    0.67, 0.59, 0.49, 0.39, 0.29, 0.21,
]

def _hour_factor(hour: int, is_weekend: bool) -> float:
    return (_WEEKEND if is_weekend else _WEEKDAY)[hour]

# Accident severity & sample descriptions for synthetic data
ACCIDENT_SEVERITIES = ["minor", "moderate", "serious", "fatal"]
ACCIDENT_DESCRIPTIONS = [
    "Rear-end collision",
    "Side-impact at intersection",
    "Vehicle left roadway",
    "Multi-vehicle pileup",
    "Single vehicle hit barrier",
    "Pedestrian involved",
    "Cyclist involved",
    "Hit and run",
    "Rollover",
]

def make_reading(loc: dict, dt: datetime) -> dict:
    is_weekend = dt.weekday() >= 5
    hf   = _hour_factor(dt.hour, is_weekend)
    base = ZONE_BASE[loc["zone"]] * ROAD_MULT[loc["road_type"]]
    noise = random.gauss(0, 0.07)
    level = int(min(100, max(0, base * hf + noise * base)))

    free_flow = 45 if loc["road_type"] == "highway" else (28 if loc["road_type"] == "segment" else 18)
    speed     = max(2.0, free_flow * (1 - level / 115) + random.gauss(0, 1.2))
    delay     = max(0.0, (free_flow / speed - 1) * random.uniform(3, 7))
    volume    = int(max(0, level * random.uniform(17, 24)))

    return {
        "id":               str(uuid4()),
        "location_id":      loc["id"],
        "timestamp":        dt.isoformat(),
        "congestion_level": level,
        "speed_mph":        round(speed, 1),
        "delay_minutes":    round(delay, 1),
        "volume":           volume,
    }

def generate():
    random.seed(42)

    locations = [
        {
            "id":        str(uuid4()),
            "name":      r[0],
            "zone":      r[1],
            "lat":       r[2],
            "lng":       r[3],
            "road_type": r[4],
        }
        for r in RAW_LOCATIONS
    ]

    now   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(days=7)
    readings = []
    ts = start
    while ts <= now:
        for loc in locations:
            readings.append(make_reading(loc, ts))
        ts += timedelta(minutes=15)

    # Generate synthetic accidents (past 30 days, random locations)
    accidents = []
    now_ts = now
    for _ in range(random.randint(18, 35)):
        loc = random.choice(locations)
        occurred = now_ts - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        severity = random.choices(ACCIDENT_SEVERITIES, weights=[40, 35, 20, 5])[0]
        vehicles = random.randint(2, 5) if severity in ("serious", "fatal") else random.randint(2, 4)
        injuries = random.randint(0, 2) if severity == "minor" else (random.randint(1, 4) if severity == "fatal" else random.randint(0, 3))
        accidents.append({
            "id": str(uuid4()),
            "location_id": loc["id"],
            "occurred_at": occurred.isoformat(),
            "severity": severity,
            "description": random.choice(ACCIDENT_DESCRIPTIONS),
            "vehicles_involved": vehicles,
            "injuries": injuries,
        })
    accidents.sort(key=lambda a: a["occurred_at"], reverse=True)

    print(f"[OK]  {len(locations)} locations")
    print(f"[OK]  {len(readings):,} readings  ({len(readings) / len(locations):.0f} per location)")
    print(f"[OK]  {len(accidents)} accidents (synthetic)")

    if USE_SUPABASE:
        print("\nUploading to Supabase ...")
        sb = create_client(_url, _key)

        # locations (upsert - safe to re-run)
        sb.table("locations").upsert(locations).execute()
        print("   - locations done")

        # readings in batches of 500
        BATCH = 500
        for i in range(0, len(readings), BATCH):
            sb.table("congestion_readings").insert(readings[i : i + BATCH]).execute()
            if (i // BATCH) % 10 == 0:
                print(f"   - readings {i:>6} / {len(readings)}")

        sb.table("accidents").insert(accidents).execute()
        print("   - accidents done")

        print("\nDatabase is ready - start the server with:  uvicorn main:app --reload")
    else:
        out = os.path.dirname(__file__)
        with open(os.path.join(out, "locations_seed.json"), "w") as f:
            json.dump(locations, f, indent=2)
        with open(os.path.join(out, "readings_seed.json"), "w") as f:
            json.dump(readings, f, indent=2)
        with open(os.path.join(out, "accidents_seed.json"), "w") as f:
            json.dump(accidents, f, indent=2)
        print("\nSaved seed files to scripts/")
        print("    Set SUPABASE_URL + SUPABASE_SERVICE_KEY in .env and re-run to upload.")

if __name__ == "__main__":
    generate()
