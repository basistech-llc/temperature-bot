-- Keep the newest active row when older deployments already contain duplicate
-- active alerts. Close each older row no earlier than its own start time or the
-- latest newer duplicate's start time, preserving a valid lifecycle interval.
UPDATE alerts AS older
SET end_time = MAX(
        older.start_time,
        COALESCE(
            (
                SELECT MAX(newer.start_time)
                FROM alerts AS newer
                WHERE newer.device_id = older.device_id
                  AND newer.alert_type = older.alert_type
                  AND newer.end_time IS NULL
                  AND newer.alert_id > older.alert_id
            ),
            older.start_time
        )
    )
WHERE older.end_time IS NULL
  AND EXISTS (
      SELECT 1
      FROM alerts AS newer
      WHERE newer.device_id = older.device_id
        AND newer.alert_type = older.alert_type
        AND newer.end_time IS NULL
        AND newer.alert_id > older.alert_id
  );

DROP INDEX IF EXISTS idx_alerts_active;

CREATE UNIQUE INDEX idx_alerts_active
    ON alerts (device_id, alert_type)
    WHERE end_time IS NULL;
