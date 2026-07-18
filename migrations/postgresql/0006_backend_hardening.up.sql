ALTER TABLE ingest_metadata
    ADD COLUMN IF NOT EXISTS partition_deleted_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_ingest_metadata_restore_pending
    ON ingest_metadata (restore_requested_at, endpoint_id, bucket_start_at)
    WHERE is_delete = FALSE AND storage_status = 'RESTORE_REQUESTED';

CREATE INDEX IF NOT EXISTS idx_ingest_metadata_archive_candidates
    ON ingest_metadata (bucket_end_at, endpoint_id, bucket_start_at)
    WHERE is_delete = FALSE AND storage_backend = 'CLICKHOUSE' AND storage_class = 'HOT';

CREATE INDEX IF NOT EXISTS idx_incidents_last_detected
    ON incidents (last_detected_at DESC, incident_id ASC)
    WHERE is_delete = FALSE;
