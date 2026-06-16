CREATE TABLE IF NOT EXISTS fcu_set_ranges (
    fcu_device_id INTEGER PRIMARY KEY,
    set_range_low_c REAL NOT NULL,
    set_range_high_c REAL NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (set_range_high_c >= set_range_low_c + 3.0),
    FOREIGN KEY (fcu_device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);
