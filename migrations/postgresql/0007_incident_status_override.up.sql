ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS status_overridden BOOLEAN NOT NULL DEFAULT FALSE;

DROP INDEX IF EXISTS idx_incidents_open_window;

CREATE INDEX idx_incidents_open_window
    ON incidents (window_end_at)
    WHERE is_delete = FALSE AND status = 'OPEN' AND status_overridden = FALSE;
