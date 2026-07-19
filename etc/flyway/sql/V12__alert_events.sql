CREATE TABLE alert_events (
    alert_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    event_time INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('triggered', 'reminder', 'resolved')),
    message TEXT NOT NULL,
    slack_status TEXT NOT NULL CHECK (slack_status IN ('pending', 'sent', 'failed')),
    -- Slack calls this value a timestamp ("ts"), but it is an opaque message
    -- identifier returned as a decimal string. Store it as TEXT to preserve the
    -- value exactly for later Slack API calls; REAL could lose precision.
    slack_message_ts TEXT,
    slack_error TEXT,
    FOREIGN KEY (alert_id) REFERENCES alerts (alert_id)
);

CREATE INDEX idx_alert_events_alert_time
    ON alert_events (alert_id, event_time DESC, alert_event_id DESC);
