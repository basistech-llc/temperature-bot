ALTER TABLE alert_events
    ADD COLUMN slack_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (slack_attempt_count >= 0);

-- Unix timestamps used for durable retry scheduling. NULL means no attempt has
-- occurred yet (last) or no future attempt is scheduled (next).
ALTER TABLE alert_events
    ADD COLUMN slack_last_attempt_time INTEGER;
ALTER TABLE alert_events
    ADD COLUMN slack_next_attempt_time INTEGER;
ALTER TABLE alert_events
    ADD COLUMN slack_terminal INTEGER NOT NULL DEFAULT 0
        CHECK (slack_terminal IN (0, 1));

UPDATE alert_events
SET slack_next_attempt_time = CASE
        WHEN slack_status IN ('pending', 'failed') THEN event_time
        ELSE NULL
    END,
    slack_terminal = CASE WHEN slack_status = 'sent' THEN 1 ELSE 0 END;

CREATE INDEX idx_alert_events_slack_outbox
    ON alert_events (slack_terminal, slack_next_attempt_time, alert_event_id)
    WHERE slack_status IN ('pending', 'failed');
