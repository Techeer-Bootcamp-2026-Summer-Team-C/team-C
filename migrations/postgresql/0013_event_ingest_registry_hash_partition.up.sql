DO $event_ingest_registry_partition_up$
DECLARE
    partition_name TEXT;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_partitioned_table
        WHERE partrelid = to_regclass('public.event_ingest_registry')
    ) THEN
        RETURN;
    END IF;

LOCK TABLE event_ingest_registry IN ACCESS EXCLUSIVE MODE;

ALTER TABLE event_ingest_registry
    RENAME TO event_ingest_registry_unpartitioned;

CREATE TABLE event_ingest_registry (
    event_id UUID NOT NULL,
    endpoint_id BIGINT NOT NULL,
    agent_id VARCHAR(64) NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_event_ingest_registry PRIMARY KEY (event_id),
    CONSTRAINT fk_event_ingest_registry_endpoint
        FOREIGN KEY (endpoint_id) REFERENCES endpoints(endpoint_id),
    CONSTRAINT ck_event_ingest_registry_payload_sha256
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$')
) PARTITION BY HASH (event_id);

CREATE TABLE event_ingest_registry_p00 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 0);
CREATE TABLE event_ingest_registry_p01 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 1);
CREATE TABLE event_ingest_registry_p02 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 2);
CREATE TABLE event_ingest_registry_p03 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 3);
CREATE TABLE event_ingest_registry_p04 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 4);
CREATE TABLE event_ingest_registry_p05 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 5);
CREATE TABLE event_ingest_registry_p06 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 6);
CREATE TABLE event_ingest_registry_p07 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 7);
CREATE TABLE event_ingest_registry_p08 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 8);
CREATE TABLE event_ingest_registry_p09 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 9);
CREATE TABLE event_ingest_registry_p10 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 10);
CREATE TABLE event_ingest_registry_p11 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 11);
CREATE TABLE event_ingest_registry_p12 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 12);
CREATE TABLE event_ingest_registry_p13 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 13);
CREATE TABLE event_ingest_registry_p14 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 14);
CREATE TABLE event_ingest_registry_p15 PARTITION OF event_ingest_registry
    FOR VALUES WITH (MODULUS 16, REMAINDER 15);

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
FROM event_ingest_registry_unpartitioned;

DROP TABLE event_ingest_registry_unpartitioned;

CREATE INDEX idx_event_ingest_registry_registered_at
    ON event_ingest_registry (registered_at);

CREATE TRIGGER tr_event_ingest_registry_append_only
BEFORE UPDATE OR DELETE ON event_ingest_registry
FOR EACH ROW
EXECUTE FUNCTION reject_event_ingest_registry_mutation();

CREATE TRIGGER tr_event_ingest_registry_no_truncate
BEFORE TRUNCATE ON event_ingest_registry
FOR EACH STATEMENT
EXECUTE FUNCTION reject_event_ingest_registry_mutation();

FOR partition_name IN
    SELECT format('event_ingest_registry_p%1$s', to_char(partition_number, 'FM00'))
    FROM generate_series(0, 15) AS partition_number
LOOP
    EXECUTE format(
        'CREATE TRIGGER tr_event_ingest_registry_no_truncate '
        'BEFORE TRUNCATE ON %I FOR EACH STATEMENT '
        'EXECUTE FUNCTION reject_event_ingest_registry_mutation()',
        partition_name
    );
END LOOP;

END
$event_ingest_registry_partition_up$;
