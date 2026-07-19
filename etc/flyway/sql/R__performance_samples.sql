-- Repeatable rather than versioned so this PR remains migration-order
-- compatible with the independent AQI/alerts branch, which owns V12-V15.
-- Flyway runs repeatable migrations after all pending versioned migrations.
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
