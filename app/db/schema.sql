
CREATE TABLE IF NOT EXISTS users (
    telegram_user_id BIGINT PRIMARY KEY,
    username TEXT,
    is_banned BOOLEAN NOT NULL DEFAULT FALSE,
    language TEXT NOT NULL DEFAULT 'en',
    database_channel_id BIGINT,
    database_channel_link TEXT,
    access_expires_at TIMESTAMPTZ,
    pair_limit INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_otp_used TEXT,
    restore_mode TEXT,
    reset_version INTEGER NOT NULL DEFAULT 0,
    reset_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS otp_keys (
    key TEXT PRIMARY KEY,
    duration_value INTEGER NOT NULL,
    duration_unit TEXT NOT NULL,
    created_by_admin BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_by_user_id BIGINT,
    used_at TIMESTAMPTZ,
    is_used BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS user_pairs (
    owner_user_id BIGINT NOT NULL REFERENCES users (telegram_user_id) ON DELETE CASCADE,
    pair_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    source_chat_id BIGINT,
    target_chat_id BIGINT,
    last_processed_id BIGINT NOT NULL DEFAULT 0,
    recent_sent_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    forward_rule BOOLEAN NOT NULL DEFAULT FALSE,
    post_rule BOOLEAN NOT NULL DEFAULT TRUE,
    scan_amount INTEGER NOT NULL DEFAULT 100,
    ads_links JSONB NOT NULL DEFAULT '[]'::jsonb,
    ban_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    post_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, pair_id)
);

CREATE INDEX IF NOT EXISTS idx_user_pairs_owner_user_id ON user_pairs(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_user_pairs_source_chat_id ON user_pairs(source_chat_id);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_logs (
    id BIGSERIAL PRIMARY KEY,
    admin_user_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO app_settings(key, value)
VALUES ('default_pair_limit', '20')
ON CONFLICT (key) DO NOTHING;
