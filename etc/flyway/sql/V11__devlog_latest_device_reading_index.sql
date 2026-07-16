CREATE INDEX IF NOT EXISTS idx_devlog_device_logtime_log_id
ON devlog (device_id, logtime DESC, log_id DESC);
