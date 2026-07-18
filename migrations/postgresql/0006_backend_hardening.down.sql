DROP INDEX IF EXISTS idx_incidents_last_detected;
DROP INDEX IF EXISTS idx_ingest_metadata_archive_candidates;
DROP INDEX IF EXISTS idx_ingest_metadata_restore_pending;
ALTER TABLE IF EXISTS ingest_metadata DROP COLUMN IF EXISTS partition_deleted_at;
