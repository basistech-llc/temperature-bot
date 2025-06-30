CREATE TABLE changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logtime INTEGER NOT NULL,
                    ipaddr TEXT NOT NULL,
                    unit INTEGER NOT NULL,
                    current_values TEXT,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                );

CREATE TABLE device_names (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE devlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    logtime INTEGER NOT NULL,
    duration INTEGER NOT NULL DEFAULT 1,
    device_id INTEGER NOT NULL,
    temp10x INTEGER,
    fanspeed INTEGER,
    FOREIGN KEY (device_id) REFERENCES device_names (id)
);

CREATE INDEX idx_templog_logtime ON devlog (logtime);
CREATE INDEX idx_templog_device_id ON devlog (device_id);
