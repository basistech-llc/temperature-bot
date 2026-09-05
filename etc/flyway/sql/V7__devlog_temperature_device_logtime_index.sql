CREATE INDEX IF NOT EXISTS idx_devlog_temperature_device_logtime
    ON devlog (device_id, logtime) WHERE temp10x IS NOT NULL;
