CREATE TABLE refresh_sessions (
    refresh_session_id UUID PRIMARY KEY,
    family_id UUID NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    token_hash CHAR(64) NOT NULL UNIQUE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    replaced_by_session_id UUID NULL REFERENCES refresh_sessions(refresh_session_id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > issued_at)
);

CREATE INDEX idx_refresh_sessions_user_active
    ON refresh_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_refresh_sessions_family
    ON refresh_sessions (family_id, issued_at DESC);
