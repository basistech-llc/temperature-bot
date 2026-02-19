CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE devices (
    device_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT UNIQUE NOT NULL
, ae200_device_id INTEGER, disabled_until INTEGER, notes TEXT, aqi_mon INTEGER DEFAULT 0);
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
                    current_values TEXT,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                , ipaddr text);
CREATE TABLE aqi (
    logtime INTEGER NOT NULL,
    aqi INTEGER NOT NULL
, co float, h float, no2 float, o3 float, p float, pm10 float, "pm25" float, so2 float, t float, w float);
CREATE INDEX idx_aqi_logtime ON aqi(logtime);
CREATE INDEX idx_aqi_aqi ON aqi(aqi);
CREATE TABLE alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,      -- 'ErrorSign', 'FilterSign', 'CheckWater'
    alert_value TEXT NOT NULL,     -- 'ON', 'OFF'
    start_time INTEGER NOT NULL,   -- Unix timestamp when alert started
    end_time INTEGER,               -- Unix timestamp when resolved (NULL if active)
    FOREIGN KEY (device_id) REFERENCES devices (device_id)
);
CREATE INDEX idx_alerts_device_id ON alerts (device_id);
CREATE INDEX idx_alerts_active ON alerts (end_time) WHERE end_time IS NULL;
CREATE INDEX idx_alerts_type ON alerts (alert_type);
CREATE INDEX idx_alerts_start_time ON alerts (start_time);
