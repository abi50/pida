CREATE TABLE IF NOT EXISTS timeline_events (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    category    TEXT NOT NULL,
    action      TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    target      TEXT NOT NULL DEFAULT '',
    detail      TEXT NOT NULL DEFAULT '{}',
    severity    TEXT NOT NULL DEFAULT 'INFO',
    timestamp   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_te_timestamp ON timeline_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_te_category  ON timeline_events(category);
CREATE INDEX IF NOT EXISTS idx_te_action    ON timeline_events(action);

CREATE TABLE IF NOT EXISTS alerts (
    id              TEXT PRIMARY KEY,
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '{}',
    acknowledged    INTEGER NOT NULL DEFAULT 0,
    snoozed_until   TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_severity   ON alerts(severity);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
