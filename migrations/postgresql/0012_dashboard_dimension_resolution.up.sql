DO $dashboard_dimension_resolution_up$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'dashboard_event_dimension_rollups'
          AND column_name = 'bucket_width_seconds'
    ) THEN
        RETURN;
    END IF;

ALTER TABLE dashboard_event_dimension_rollups
    ADD COLUMN IF NOT EXISTS bucket_width_seconds INTEGER NOT NULL DEFAULT 60;

ALTER TABLE dashboard_event_dimension_rollups
    DROP CONSTRAINT IF EXISTS dashboard_event_dimension_rollups_pkey;

ALTER TABLE dashboard_event_dimension_rollups
    ADD CONSTRAINT dashboard_event_dimension_rollups_pkey
    PRIMARY KEY (
        bucket_start_at,
        endpoint_id,
        dimension_name,
        dimension_value,
        bucket_width_seconds
    );

ALTER TABLE dashboard_event_dimension_rollups
    DROP CONSTRAINT IF EXISTS ck_dashboard_event_dimension_rollups_bucket_width;

ALTER TABLE dashboard_event_dimension_rollups
    ADD CONSTRAINT ck_dashboard_event_dimension_rollups_bucket_width
    CHECK (bucket_width_seconds IN (60, 300, 3600, 86400));

END
$dashboard_dimension_resolution_up$;
