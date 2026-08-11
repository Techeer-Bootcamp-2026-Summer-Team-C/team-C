CREATE TABLE dashboard_event_rollups (
    bucket_start_at TIMESTAMPTZ NOT NULL,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL CHECK (
        event_type IN ('PROCESS_EXECUTION', 'NETWORK_CONNECTION', 'FILE_EVENT', 'DNS_QUERY', 'L7_EVENT')
    ),
    event_count BIGINT NOT NULL CHECK (event_count >= 0),
    source_max_ingested_at TIMESTAMPTZ NULL,
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (bucket_start_at, endpoint_id, event_type)
);

CREATE INDEX idx_dashboard_event_rollups_endpoint_bucket
    ON dashboard_event_rollups (endpoint_id, bucket_start_at);

CREATE TABLE dashboard_event_dimension_rollups (
    bucket_start_at TIMESTAMPTZ NOT NULL,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id) ON DELETE CASCADE,
    dimension_name VARCHAR(30) NOT NULL CHECK (
        dimension_name IN (
            'top_processes',
            'top_remote_ips',
            'top_domains',
            'top_file_hashes',
            'top_dns_queries',
            'top_l7_protocols'
        )
    ),
    dimension_value TEXT NOT NULL CHECK (dimension_value <> ''),
    bucket_width_seconds INTEGER NOT NULL CHECK (bucket_width_seconds IN (60, 300, 3600, 86400)),
    event_count BIGINT NOT NULL CHECK (event_count >= 0),
    refreshed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (bucket_start_at, endpoint_id, dimension_name, dimension_value, bucket_width_seconds)
);

CREATE INDEX idx_dashboard_event_dimension_rollups_endpoint_bucket
    ON dashboard_event_dimension_rollups (endpoint_id, bucket_start_at);

CREATE TABLE dashboard_rollup_state (
    rollup_name VARCHAR(100) PRIMARY KEY,
    covered_from TIMESTAMPTZ NULL,
    covered_through TIMESTAMPTZ NULL,
    source_max_ingested_at TIMESTAMPTZ NULL,
    refreshed_at TIMESTAMPTZ NOT NULL,
    CHECK (covered_from IS NULL OR covered_through IS NULL OR covered_from <= covered_through)
);
