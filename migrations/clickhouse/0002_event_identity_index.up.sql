ALTER TABLE edr_events
    ADD INDEX IF NOT EXISTS idx_edr_events_event_id event_id TYPE bloom_filter(0.001) GRANULARITY 1;
