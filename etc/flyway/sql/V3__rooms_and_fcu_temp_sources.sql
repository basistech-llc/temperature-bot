CREATE TABLE IF NOT EXISTS rooms (
    room_id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT NOT NULL UNIQUE,
    map_json TEXT NOT NULL DEFAULT '{}'
);

ALTER TABLE devices ADD COLUMN room_id INTEGER REFERENCES rooms(room_id);

CREATE TABLE IF NOT EXISTS fcu_temp_sources (
    fcu_device_id INTEGER NOT NULL,
    source_device_id INTEGER NOT NULL,
    multiplier REAL NOT NULL CHECK (multiplier >= 0),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (fcu_device_id, source_device_id),
    FOREIGN KEY (fcu_device_id) REFERENCES devices(device_id),
    FOREIGN KEY (source_device_id) REFERENCES devices(device_id)
);

CREATE INDEX IF NOT EXISTS idx_devices_room_id ON devices(room_id);
CREATE INDEX IF NOT EXISTS idx_fcu_temp_sources_source_device_id
    ON fcu_temp_sources(source_device_id);
