-- Cloudflare D1 database "mikeytech": data that must be collected 24/7 without the PC.

-- JOSHY demo licenses, one row per installation (hardware id). Mirrors e-profile's
-- content/audio_suite_licenses.json records.
CREATE TABLE IF NOT EXISTS joshy_licenses (
  hwid            TEXT PRIMARY KEY,
  first_run       INTEGER NOT NULL,
  last_seen       INTEGER NOT NULL,
  duration_days   INTEGER NOT NULL DEFAULT 14,
  app_version     TEXT,
  remote_revoked  INTEGER NOT NULL DEFAULT 0,
  status          TEXT
);
CREATE INDEX IF NOT EXISTS joshy_licenses_last_seen ON joshy_licenses(last_seen);

-- JOSHY in-app feedback (bug reports, suggestions).
CREATE TABLE IF NOT EXISTS joshy_feedback (
  id              TEXT PRIMARY KEY,
  hwid            TEXT,
  type            TEXT,
  subject         TEXT,
  message         TEXT,
  app_version     TEXT,
  timestamp       INTEGER NOT NULL,
  formatted_time  TEXT
);
CREATE INDEX IF NOT EXISTS joshy_feedback_ts ON joshy_feedback(timestamp);

-- Echos Lab sound calibrator results (columns of e-profile's calibration_data.csv).
CREATE TABLE IF NOT EXISTS echos_calibration (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  INTEGER NOT NULL,
  time_text   TEXT,
  user        TEXT,
  x           TEXT,
  z           TEXT,
  key         TEXT,
  dir         TEXT,
  comment     TEXT
);

-- Small key/value settings, e.g. 'joshy_releases' = e-profile's audio_suite_releases.json.
CREATE TABLE IF NOT EXISTS settings (
  key    TEXT PRIMARY KEY,
  value  TEXT NOT NULL
);

-- JOSHY download clicks on the e-profile site (files themselves come from GitHub releases).
CREATE TABLE IF NOT EXISTS joshy_downloads (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at   INTEGER NOT NULL,
  package_id   TEXT NOT NULL,
  client_hash  TEXT,
  user_agent   TEXT
);

-- Newsletter requests received while the PC was offline; CyberBrief applies them later.
CREATE TABLE IF NOT EXISTS newsletter_queue (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at    INTEGER NOT NULL,
  action        TEXT NOT NULL,      -- 'subscribe' | 'unsubscribe'
  payload       TEXT NOT NULL,      -- JSON body / query as received
  processed_at  INTEGER
);
