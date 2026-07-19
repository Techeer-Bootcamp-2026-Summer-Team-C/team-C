CREATE TABLE users (
    user_id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN ('ADMIN', 'ANALYST', 'VIEWER')),
    status VARCHAR(30) NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    last_login_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX uq_users_email_active ON users (LOWER(email)) WHERE is_delete = FALSE;

CREATE TABLE endpoints (
    endpoint_id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(64) NOT NULL UNIQUE,
    hostname VARCHAR(255) NOT NULL,
    os_type VARCHAR(30) NOT NULL CHECK (os_type IN ('WINDOWS', 'MACOS')),
    os_version VARCHAR(100) NULL,
    ip_address INET NULL,
    agent_version VARCHAR(50) NULL,
    agent_build_id VARCHAR(200) NULL,
    agent_arch VARCHAR(20) NULL CHECK (agent_arch IS NULL OR agent_arch IN ('X64', 'ARM64')),
    capability_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(capability_codes_json) = 'array'),
    sensor_health_json JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(sensor_health_json) = 'array'),
    registered_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN ('ONLINE', 'OFFLINE', 'RETIRED')),
    last_seen_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_endpoints_status_last_seen ON endpoints (status, last_seen_at) WHERE is_delete = FALSE;

CREATE TABLE agent_auth_keys (
    agent_auth_key_id BIGSERIAL PRIMARY KEY,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id),
    cert_fingerprint VARCHAR(128) NOT NULL UNIQUE,
    cert_subject VARCHAR(500) NOT NULL,
    cert_san_agent_id VARCHAR(64) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_agent_auth_keys_endpoint ON agent_auth_keys (endpoint_id);
CREATE UNIQUE INDEX uq_agent_auth_keys_one_active
    ON agent_auth_keys (endpoint_id)
    WHERE is_delete = FALSE AND revoked_at IS NULL;

CREATE TABLE audit_logs (
    audit_log_id BIGSERIAL PRIMARY KEY,
    actor_type VARCHAR(30) NOT NULL CHECK (actor_type IN ('USER', 'AGENT', 'SYSTEM')),
    actor_identifier VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    before_json JSONB NULL,
    after_json JSONB NULL,
    request_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_audit_logs_resource_created ON audit_logs (resource_type, resource_id, created_at);
CREATE INDEX idx_audit_logs_request_id ON audit_logs (request_id);

CREATE TABLE ingest_metadata (
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id),
    bucket_start_at TIMESTAMPTZ NOT NULL,
    bucket_end_at TIMESTAMPTZ NOT NULL,
    storage_backend VARCHAR(30) NOT NULL CHECK (storage_backend IN ('CLICKHOUSE', 'S3')),
    storage_class VARCHAR(50) NOT NULL CHECK (storage_class IN ('HOT', 'GLACIER_FLEXIBLE_RETRIEVAL')),
    storage_status VARCHAR(30) NOT NULL CHECK (
        storage_status IN ('HOT', 'ARCHIVED', 'RESTORE_REQUESTED', 'RESTORED', 'RESTORE_FAILED', 'EXPIRED')
    ),
    storage_path VARCHAR(1000) NOT NULL,
    event_count BIGINT NOT NULL DEFAULT 0 CHECK (event_count >= 0),
    size_bytes BIGINT NULL CHECK (size_bytes IS NULL OR size_bytes >= 0),
    checksum_sha256 CHAR(64) NULL,
    archived_at TIMESTAMPTZ NULL,
    archive_verified_at TIMESTAMPTZ NULL,
    restore_requested_at TIMESTAMPTZ NULL,
    restored_at TIMESTAMPTZ NULL,
    restore_expires_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    partition_deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (endpoint_id, bucket_start_at, storage_backend, storage_class),
    UNIQUE (storage_backend, storage_path),
    CHECK (bucket_start_at < bucket_end_at),
    CHECK (
        (storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT' AND storage_status = 'HOT')
        OR
        (storage_backend = 'S3' AND storage_class = 'GLACIER_FLEXIBLE_RETRIEVAL' AND storage_status <> 'HOT')
    )
);

CREATE INDEX idx_ingest_metadata_overlap
    ON ingest_metadata (endpoint_id, bucket_start_at, bucket_end_at)
    WHERE is_delete = FALSE;

CREATE INDEX idx_ingest_metadata_restore_pending
    ON ingest_metadata (restore_requested_at, endpoint_id, bucket_start_at)
    WHERE is_delete = FALSE AND storage_status = 'RESTORE_REQUESTED';

CREATE INDEX idx_ingest_metadata_archive_candidates
    ON ingest_metadata (bucket_end_at, endpoint_id, bucket_start_at)
    WHERE is_delete = FALSE AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT';

CREATE TABLE alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id),
    event_id UUID NOT NULL,
    event_occurred_at TIMESTAMPTZ NOT NULL,
    batch_id UUID NULL,
    agent_id VARCHAR(64) NOT NULL,
    rule_code VARCHAR(100) NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    rule_version INTEGER NOT NULL CHECK (rule_version >= 1),
    mitre_tactic_code VARCHAR(20) NOT NULL,
    mitre_tactic_name VARCHAR(100) NOT NULL,
    mitre_technique_code VARCHAR(30) NOT NULL,
    mitre_technique_name VARCHAR(200) NOT NULL,
    title VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    risk_score NUMERIC(5,2) NOT NULL CHECK (risk_score >= 0 AND risk_score <= 100),
    status VARCHAR(30) NOT NULL CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
    detected_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (event_id, rule_code, rule_version)
);

CREATE INDEX idx_alerts_endpoint_detected ON alerts (endpoint_id, detected_at DESC) WHERE is_delete = FALSE;
CREATE INDEX idx_alerts_active_risk ON alerts (endpoint_id, rule_code, rule_version, risk_score DESC)
    WHERE is_delete = FALSE AND status IN ('OPEN', 'IN_PROGRESS');

CREATE TABLE incidents (
    incident_id BIGSERIAL PRIMARY KEY,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id),
    correlation_key VARCHAR(255) NOT NULL,
    window_start_at TIMESTAMPTZ NOT NULL,
    window_end_at TIMESTAMPTZ NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status VARCHAR(30) NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    first_detected_at TIMESTAMPTZ NOT NULL,
    last_detected_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (endpoint_id, correlation_key, window_start_at),
    CHECK (window_start_at < window_end_at),
    CHECK ((status = 'OPEN' AND closed_at IS NULL) OR (status = 'CLOSED' AND closed_at = window_end_at))
);

CREATE INDEX idx_incidents_endpoint_last_detected
    ON incidents (endpoint_id, last_detected_at DESC) WHERE is_delete = FALSE;
CREATE INDEX idx_incidents_last_detected
    ON incidents (last_detected_at DESC, incident_id ASC) WHERE is_delete = FALSE;
CREATE INDEX idx_incidents_open_window
    ON incidents (window_end_at) WHERE is_delete = FALSE AND status = 'OPEN';

CREATE TABLE incident_alerts (
    incident_alert_id BIGSERIAL PRIMARY KEY,
    incident_id BIGINT NOT NULL REFERENCES incidents(incident_id),
    alert_id BIGINT NOT NULL REFERENCES alerts(alert_id),
    linked_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_delete BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (incident_id, alert_id)
);
