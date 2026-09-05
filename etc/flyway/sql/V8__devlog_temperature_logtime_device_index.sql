CREATE INDEX IF NOT EXISTS idx_devlog_temperature_logtime_device
    ON devlog (logtime, device_id) WHERE temp10x IS NOT NULL;
