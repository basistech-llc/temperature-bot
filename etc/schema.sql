CREATE TABLE devices (
    device_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT UNIQUE NOT NULL
, ae200_device_id INTEGER, disabled_until INTEGER, notes TEXT);
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
CREATE TABLE changelog (
                    changelog_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logtime INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    unit INTEGER,
                    ipaddr TEXT,
                    current_values TEXT,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                );
CREATE TABLE aqi (
    logtime INTEGER NOT NULL,
    aqi INTEGER NOT NULL
, co float, h float, no2 float, o3 float, p float, pm10 float, "pm25" float, so2 float, t float, w float);
CREATE INDEX idx_aqi_logtime ON aqi(logtime);
CREATE INDEX idx_aqi_aqi ON aqi(aqi);
