CREATE TABLE presence_events (
    presence_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL REFERENCES devices(device_id),
    room_id INTEGER REFERENCES rooms(room_id),
    observed_at INTEGER NOT NULL,
    present INTEGER NOT NULL CHECK (present IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_presence_events_room_observed_at
ON presence_events(room_id, observed_at);

CREATE INDEX IF NOT EXISTS idx_presence_events_device_observed_at
ON presence_events(device_id, observed_at);
