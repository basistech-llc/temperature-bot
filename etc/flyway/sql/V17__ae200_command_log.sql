-- Durable audit trail for commands sent to the AE-200 controller.
-- Times are Unix epoch milliseconds stored as INTEGER so they sort and compare
-- numerically. JSON is TEXT because SQLite has no separate JSON storage class;
-- json_valid() ensures that the stored request and response remain valid JSON.
CREATE TABLE ae200_command_log (
    command_id INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_at_ms INTEGER NOT NULL,
    completed_at_ms INTEGER NOT NULL,
    instance_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    ae200_device_id TEXT NOT NULL,
    request_json TEXT NOT NULL CHECK (json_valid(request_json)),
    outcome TEXT NOT NULL CHECK (outcome IN ('confirmed', 'simulated', 'error')),
    response_summary TEXT NOT NULL,
    response_json TEXT CHECK (response_json IS NULL OR json_valid(response_json)),
    error_type TEXT,
    error_message TEXT
);

CREATE INDEX idx_ae200_command_log_requested_at
ON ae200_command_log(requested_at_ms DESC, command_id DESC);
