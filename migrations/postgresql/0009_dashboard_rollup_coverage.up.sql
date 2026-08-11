CREATE TABLE dashboard_rollup_coverage (
    rollup_name VARCHAR(100) NOT NULL REFERENCES dashboard_rollup_state(rollup_name) ON DELETE CASCADE,
    bucket_start_at TIMESTAMPTZ NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (rollup_name, bucket_start_at)
);

CREATE INDEX idx_dashboard_rollup_coverage_bucket
    ON dashboard_rollup_coverage (bucket_start_at, rollup_name);
