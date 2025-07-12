CREATE TABLE changelog (
                    changelog_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logtime INTEGER NOT NULL,
                    ipaddr TEXT NOT NULL,
                    device_id INTEGER NOT NULL,
                    current_values TEXT,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                );

CREATE TABLE devices (
    device_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT UNIQUE NOT NULL,
    ae200_device_id INTEGER
);

CREATE INDEX idx_devices_device_name ON devices (device_name);

CREATE TABLE devlog (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    logtime INTEGER NOT NULL,
    duration INTEGER NOT NULL DEFAULT 1,
    temp10x INTEGER,
    status_json TEXT,
    FOREIGN KEY (device_id) REFERENCES devices (device_id)
);

CREATE INDEX idx_templog_logtime ON devlog (logtime);
CREATE INDEX idx_templog_device_id ON devlog (device_id);
