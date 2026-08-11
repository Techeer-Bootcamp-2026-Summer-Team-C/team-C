DO $dashboard_dimension_resolution_down$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'dashboard_event_dimension_rollups'
          AND column_name = 'bucket_width_seconds'
    ) THEN
        RETURN;
    END IF;

DELETE FROM dashboard_event_dimension_rollups
WHERE bucket_width_seconds <> 60;

ALTER TABLE dashboard_event_dimension_rollups
    DROP CONSTRAINT IF EXISTS dashboard_event_dimension_rollups_pkey;

ALTER TABLE dashboard_event_dimension_rollups
    DROP CONSTRAINT IF EXISTS ck_dashboard_event_dimension_rollups_bucket_width;

ALTER TABLE dashboard_event_dimension_rollups
    DROP COLUMN IF EXISTS bucket_width_seconds;

ALTER TABLE dashboard_event_dimension_rollups
    ADD CONSTRAINT dashboard_event_dimension_rollups_pkey
    PRIMARY KEY (bucket_start_at, endpoint_id, dimension_name, dimension_value);

END
$dashboard_dimension_resolution_down$;
