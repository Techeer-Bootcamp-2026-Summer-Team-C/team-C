DROP TRIGGER IF EXISTS tr_event_ingest_registry_no_truncate ON event_ingest_registry;
DROP TRIGGER IF EXISTS tr_event_ingest_registry_append_only ON event_ingest_registry;
DROP FUNCTION IF EXISTS reject_event_ingest_registry_mutation();
