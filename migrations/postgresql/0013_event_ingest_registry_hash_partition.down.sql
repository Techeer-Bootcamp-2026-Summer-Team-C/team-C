DO $event_ingest_registry_partition_down$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_partitioned_table
        WHERE partrelid = to_regclass('public.event_ingest_registry')
    ) THEN
        RETURN;
    END IF;

LOCK TABLE event_ingest_registry IN ACCESS EXCLUSIVE MODE;

ALTER TABLE event_ingest_registry
    RENAME TO event_ingest_registry_partitioned;

CREATE TABLE event_ingest_registry (
    event_id UUID PRIMARY KEY,
    endpoint_id BIGINT NOT NULL REFERENCES endpoints(endpoint_id),
    agent_id VARCHAR(64) NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_event_ingest_registry_payload_sha256
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$')
);

INSERT INTO event_ingest_registry (
    event_id,
    endpoint_id,
    agent_id,
    payload_sha256,
    registered_at
)
SELECT
    event_id,
    endpoint_id,
    agent_id,
    payload_sha256,
    registered_at
FROM event_ingest_registry_partitioned;

DROP TABLE event_ingest_registry_partitioned;

CREATE TRIGGER tr_event_ingest_registry_append_only
BEFORE UPDATE OR DELETE ON event_ingest_registry
FOR EACH ROW
EXECUTE FUNCTION reject_event_ingest_registry_mutation();

CREATE TRIGGER tr_event_ingest_registry_no_truncate
BEFORE TRUNCATE ON event_ingest_registry
FOR EACH STATEMENT
EXECUTE FUNCTION reject_event_ingest_registry_mutation();

END
$event_ingest_registry_partition_down$;
