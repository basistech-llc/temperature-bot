CREATE TABLE IF NOT EXISTS devices (
    device_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT UNIQUE NOT NULL
, ae200_device_id INTEGER, disabled_until INTEGER, notes TEXT, aqi_mon INTEGER DEFAULT 0, room_id INTEGER REFERENCES rooms(room_id), display_name TEXT, device_type TEXT, rules_enabled INTEGER NOT NULL DEFAULT 1, device_subtype TEXT);
CREATE INDEX IF NOT EXISTS idx_devices_device_name ON devices (device_name);
CREATE TABLE IF NOT EXISTS devlog (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    logtime INTEGER NOT NULL,
    duration INTEGER NOT NULL DEFAULT 1,
    temp10x INTEGER,
    status_json TEXT,
    FOREIGN KEY (device_id) REFERENCES devices (device_id)
);
CREATE INDEX IF NOT EXISTS idx_templog_logtime ON devlog (logtime);
CREATE INDEX IF NOT EXISTS idx_templog_device_id ON devlog (device_id);
CREATE TABLE IF NOT EXISTS changelog (
                    changelog_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logtime INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    unit INTEGER,
                    current_values TEXT,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                , ipaddr text);
CREATE TABLE IF NOT EXISTS aqi (
    logtime INTEGER NOT NULL,
    aqi INTEGER NOT NULL
, co float, h float, no2 float, o3 float, p float, pm10 float, "pm25" float, so2 float, t float, w float);
CREATE INDEX IF NOT EXISTS idx_aqi_logtime ON aqi(logtime);
CREATE INDEX IF NOT EXISTS idx_aqi_aqi ON aqi(aqi);
CREATE TABLE IF NOT EXISTS alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,      -- 'ErrorSign', 'FilterSign', 'CheckWater'
    alert_value TEXT NOT NULL,     -- 'ON', 'OFF'
    start_time INTEGER NOT NULL,   -- Unix timestamp when alert started
    end_time INTEGER,               -- Unix timestamp when resolved (NULL if active)
    FOREIGN KEY (device_id) REFERENCES devices (device_id)
);
CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts (device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts (alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_start_time ON alerts (start_time);
CREATE INDEX IF NOT EXISTS idx_changelog_logtime ON changelog (logtime);
CREATE INDEX IF NOT EXISTS idx_changelog_device_id_logtime ON changelog (device_id, logtime);
CREATE TABLE IF NOT EXISTS rooms (
    room_id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_name TEXT NOT NULL UNIQUE,
    map_json TEXT NOT NULL DEFAULT '{}'
, fcu_device_id INTEGER REFERENCES devices(device_id));
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
CREATE TABLE IF NOT EXISTS fcu_set_ranges (
    fcu_device_id INTEGER PRIMARY KEY,
    set_range_low_c REAL NOT NULL,
    set_range_high_c REAL NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (set_range_high_c >= set_range_low_c + 3.0),
    FOREIGN KEY (fcu_device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_devlog_temperature_device_logtime
    ON devlog (device_id, logtime) WHERE temp10x IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_devlog_temperature_logtime_device
    ON devlog (logtime, device_id) WHERE temp10x IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_rooms_fcu_device_id
ON rooms(fcu_device_id)
WHERE fcu_device_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_fcu_room_id
ON devices(room_id)
WHERE device_type = 'FCU' AND room_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS presence_events (
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
CREATE INDEX IF NOT EXISTS idx_devlog_device_logtime_log_id
ON devlog (device_id, logtime DESC, log_id DESC);
CREATE TABLE IF NOT EXISTS alert_events (
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
    slack_error TEXT, slack_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (slack_attempt_count >= 0), slack_last_attempt_time INTEGER, slack_next_attempt_time INTEGER, slack_terminal INTEGER NOT NULL DEFAULT 0
        CHECK (slack_terminal IN (0, 1)),
    FOREIGN KEY (alert_id) REFERENCES alerts (alert_id)
);
CREATE INDEX IF NOT EXISTS idx_alert_events_alert_time
    ON alert_events (alert_id, event_time DESC, alert_event_id DESC);
CREATE INDEX IF NOT EXISTS idx_alert_events_slack_outbox
    ON alert_events (slack_terminal, slack_next_attempt_time, alert_event_id)
    WHERE slack_status IN ('pending', 'failed');
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_active
    ON alerts (device_id, alert_type)
    WHERE end_time IS NULL;
CREATE TABLE IF NOT EXISTS performance_samples (
    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at_ms INTEGER NOT NULL,
    instance_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    sample_type TEXT NOT NULL,
    operation TEXT NOT NULL,
    target_host TEXT NOT NULL,
    target_port INTEGER,
    resolved_ip TEXT,
    ae200_device_id TEXT,
    dns_ms REAL CHECK (dns_ms IS NULL OR dns_ms >= 0),
    icmp_min_ms REAL CHECK (icmp_min_ms IS NULL OR icmp_min_ms >= 0),
    icmp_median_ms REAL CHECK (icmp_median_ms IS NULL OR icmp_median_ms >= 0),
    icmp_max_ms REAL CHECK (icmp_max_ms IS NULL OR icmp_max_ms >= 0),
    packet_loss_pct REAL CHECK (
        packet_loss_pct IS NULL OR
        (packet_loss_pct >= 0 AND packet_loss_pct <= 100)
    ),
    lock_wait_ms REAL CHECK (lock_wait_ms IS NULL OR lock_wait_ms >= 0),
    connect_ms REAL CHECK (connect_ms IS NULL OR connect_ms >= 0),
    response_ms REAL CHECK (response_ms IS NULL OR response_ms >= 0),
    close_ms REAL CHECK (close_ms IS NULL OR close_ms >= 0),
    total_ms REAL NOT NULL CHECK (total_ms >= 0),
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    outcome TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    response_bytes INTEGER CHECK (response_bytes IS NULL OR response_bytes >= 0),
    experiment_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_performance_samples_observed_at
ON performance_samples(observed_at_ms);
CREATE INDEX IF NOT EXISTS idx_performance_samples_instance_type_time
ON performance_samples(instance_id, sample_type, observed_at_ms);
CREATE INDEX IF NOT EXISTS idx_performance_samples_operation_time
ON performance_samples(operation, observed_at_ms);
