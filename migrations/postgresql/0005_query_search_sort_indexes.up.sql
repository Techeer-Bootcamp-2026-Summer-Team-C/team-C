CREATE INDEX IF NOT EXISTS idx_endpoints_hostname_lower_prefix
    ON endpoints ((LOWER(hostname)) text_pattern_ops)
    WHERE is_delete = FALSE;

CREATE INDEX IF NOT EXISTS idx_endpoints_agent_id_lower_prefix
    ON endpoints ((LOWER(agent_id)) text_pattern_ops)
    WHERE is_delete = FALSE;

CREATE INDEX IF NOT EXISTS idx_alerts_detected_at
    ON alerts (detected_at DESC, alert_id ASC)
    WHERE is_delete = FALSE;
