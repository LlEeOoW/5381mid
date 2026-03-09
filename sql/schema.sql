-- ================================================================
-- CITYFLOW — SUPABASE SCHEMA
-- Paste this entire file into Supabase → SQL Editor → Run
-- ================================================================

-- 1. Locations (static metadata for each monitored point)
CREATE TABLE IF NOT EXISTS locations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  zone        TEXT NOT NULL,         -- e.g. "Midtown", "Downtown"
  lat         FLOAT NOT NULL,
  lng         FLOAT NOT NULL,
  road_type   TEXT NOT NULL          -- 'intersection' | 'segment' | 'highway'
                CHECK (road_type IN ('intersection','segment','highway')),
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Congestion readings (time-series, the core table)
CREATE TABLE IF NOT EXISTS congestion_readings (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id      UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  timestamp        TIMESTAMPTZ NOT NULL,
  congestion_level INTEGER NOT NULL CHECK (congestion_level BETWEEN 0 AND 100),
  speed_mph        FLOAT NOT NULL,
  delay_minutes    FLOAT NOT NULL,
  volume           INTEGER NOT NULL,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Fast query indexes
CREATE INDEX IF NOT EXISTS idx_readings_ts   ON congestion_readings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_readings_loc  ON congestion_readings(location_id);
CREATE INDEX IF NOT EXISTS idx_readings_lvl  ON congestion_readings(congestion_level DESC);
CREATE INDEX IF NOT EXISTS idx_loc_zone      ON locations(zone);

-- Row-level security (open reads for the dashboard)
ALTER TABLE locations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE congestion_readings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_locations"  ON locations           FOR SELECT USING (true);
CREATE POLICY "public_read_readings"   ON congestion_readings FOR SELECT USING (true);
CREATE POLICY "service_insert_locs"    ON locations           FOR INSERT WITH CHECK (true);
CREATE POLICY "service_insert_reads"   ON congestion_readings FOR INSERT WITH CHECK (true);

-- 3. Accidents / crash reports (current & historical)
CREATE TABLE IF NOT EXISTS accidents (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id       UUID REFERENCES locations(id) ON DELETE SET NULL,
  occurred_at       TIMESTAMPTZ NOT NULL,
  severity          TEXT NOT NULL CHECK (severity IN ('minor','moderate','serious','fatal')),
  description       TEXT,
  vehicles_involved INTEGER NOT NULL DEFAULT 2 CHECK (vehicles_involved >= 1),
  injuries          INTEGER NOT NULL DEFAULT 0 CHECK (injuries >= 0),
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accidents_occurred ON accidents(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_accidents_location ON accidents(location_id);
CREATE INDEX IF NOT EXISTS idx_accidents_severity ON accidents(severity);

ALTER TABLE accidents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_accidents" ON accidents FOR SELECT USING (true);
CREATE POLICY "service_insert_accidents" ON accidents FOR INSERT WITH CHECK (true);

-- Convenience view: one latest reading per location (used by /api/current)
CREATE OR REPLACE VIEW latest_congestion AS
SELECT DISTINCT ON (cr.location_id)
  cr.location_id,
  l.name, l.zone, l.lat, l.lng, l.road_type,
  cr.timestamp,
  cr.congestion_level,
  cr.speed_mph,
  cr.delay_minutes,
  cr.volume
FROM congestion_readings cr
JOIN locations l ON l.id = cr.location_id
ORDER BY cr.location_id, cr.timestamp DESC;
