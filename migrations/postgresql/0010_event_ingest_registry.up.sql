CREATE TABLE event_ingest_registry (
    event_id UUID PRIMARY KEY,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id),
    agent_id VARCHAR(64) NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_event_ingest_registry_payload_sha256
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$')
);
