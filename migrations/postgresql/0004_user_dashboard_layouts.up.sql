CREATE TABLE user_dashboard_layouts (
    layout_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    dashboard_key VARCHAR(64) NOT NULL,
    layout_version INTEGER NOT NULL CHECK (layout_version >= 1),
    revision BIGINT NOT NULL CHECK (revision >= 1),
    layout_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_user_dashboard_layouts_user_dashboard UNIQUE (user_id, dashboard_key),
    CONSTRAINT ck_user_dashboard_layouts_json_array CHECK (jsonb_typeof(layout_json) = 'array')
);

CREATE INDEX idx_user_dashboard_layouts_user_id ON user_dashboard_layouts (user_id);
