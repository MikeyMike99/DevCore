-- Apply to the existing D1 database (not applied yet):
--   wrangler d1 execute mikeytech --remote --file=labkit/lab_schema.sql
CREATE TABLE IF NOT EXISTS lab_progress (
  id          TEXT PRIMARY KEY,          -- client request id: makes offline replays idempotent
  learner     TEXT NOT NULL,
  lab         TEXT NOT NULL,
  step        TEXT NOT NULL,
  command     TEXT NOT NULL,
  client_ts   INTEGER NOT NULL,
  replayed    INTEGER NOT NULL DEFAULT 0,
  received_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lab_progress_learner ON lab_progress (learner, lab);
