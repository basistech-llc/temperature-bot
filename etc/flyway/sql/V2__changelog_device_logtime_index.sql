DROP INDEX IF EXISTS idx_changelog_device_id;
CREATE INDEX IF NOT EXISTS idx_changelog_device_id_logtime ON changelog (device_id, logtime);
