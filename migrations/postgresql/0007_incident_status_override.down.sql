DROP INDEX IF EXISTS idx_incidents_open_window;

ALTER TABLE IF EXISTS incidents
    DROP COLUMN IF EXISTS status_overridden;
