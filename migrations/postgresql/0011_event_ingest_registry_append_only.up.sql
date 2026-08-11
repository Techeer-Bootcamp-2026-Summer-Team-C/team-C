CREATE FUNCTION reject_event_ingest_registry_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $event_ingest_registry_append_only$
BEGIN
    RAISE EXCEPTION 'event_ingest_registry is append-only'
        USING ERRCODE = '55000';
END;
$event_ingest_registry_append_only$;

CREATE TRIGGER tr_event_ingest_registry_append_only
BEFORE UPDATE OR DELETE ON event_ingest_registry
FOR EACH ROW
EXECUTE FUNCTION reject_event_ingest_registry_mutation();

CREATE TRIGGER tr_event_ingest_registry_no_truncate
BEFORE TRUNCATE ON event_ingest_registry
FOR EACH STATEMENT
EXECUTE FUNCTION reject_event_ingest_registry_mutation();
