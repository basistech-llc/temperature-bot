-- Unsolicited AE-200 notifyRequest observations. These are deliberately not
-- classified as autonomous: the protocol does not identify whether a schedule,
-- wall controller, web user, or Temperature Bot caused a reported change.
CREATE TABLE ae200_notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at_ms INTEGER NOT NULL,
    instance_id TEXT NOT NULL,
    ae200_group_id TEXT,
    ae200_address TEXT,
    values_json TEXT NOT NULL CHECK (json_valid(values_json)),
    CHECK (ae200_group_id IS NOT NULL OR ae200_address IS NOT NULL)
);

CREATE INDEX idx_ae200_notifications_observed_at
ON ae200_notifications(observed_at_ms DESC, notification_id DESC);
