"""
Quick check: Supabase .env and tables.
Run from project root:  python check_supabase.py
"""
import os
from pathlib import Path

# load .env from project root (same folder as this file)
import dotenv
dotenv.load_dotenv(Path(__file__).resolve().parent / ".env")

url = os.environ.get("SUPABASE_URL", "").strip()
key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

print("1. .env")
if not url:
    print("   SUPABASE_URL is empty")
    exit(1)
if url.startswith("https://YOUR"):
    print("   SUPABASE_URL still placeholder (YOUR_PROJECT_ID)")
    exit(1)
print(f"   SUPABASE_URL = {url[:40]}...")

if not key or len(key) < 50:
    print("   SUPABASE_SERVICE_KEY missing or too short (need long JWT)")
    exit(1)
print(f"   SUPABASE_SERVICE_KEY = eyJ... ({len(key)} chars)")

print("\n2. Connect and query")
try:
    from supabase import create_client
    sb = create_client(url, key)
except Exception as e:
    print(f"   Failed to create client: {e}")
    exit(1)

for table in ["locations", "congestion_readings", "accidents", "latest_congestion"]:
    try:
        r = sb.table(table).select("*").limit(1).execute()
        n = len(r.data or [])
        print(f"   {table}: OK (sample rows = {n})")
    except Exception as e:
        print(f"   {table}: FAIL - {e}")
        exit(1)

print("\n[OK] Supabase and tables are ready. Run: python generate_data.py  then  python main.py")
