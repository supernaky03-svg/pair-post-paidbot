from __future__ import annotations

from app.db.connection import execute

MIGRATIONS = [
    '''
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        language TEXT NOT NULL DEFAULT 'en',
        status TEXT NOT NULL DEFAULT 'not_activated',
        activated_until TIMESTAMPTZ,
        is_banned BOOLEAN NOT NULL DEFAULT FALSE,
        pair_limit_override INTEGER,
        needs_restore_choice BOOLEAN NOT NULL DEFAULT FALSE,
        current_generation INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS otp_keys (
        key_hash TEXT PRIMARY KEY,
        duration_code TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_by_admin BIGINT,
        is_used BOOLEAN NOT NULL DEFAULT FALSE,
        redeemed_by_user_id BIGINT,
        redeemed_at TIMESTAMPTZ,
        activated_until TIMESTAMPTZ
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS global_settings (
        key TEXT PRIMARY KEY,
        value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS sources (
        source_key TEXT PRIMARY KEY,
        source_input TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        normalized_value TEXT NOT NULL,
        invite_hash TEXT,
        joined_by_shared_session BOOLEAN NOT NULL DEFAULT FALSE,
        active_pair_reference_count INTEGER NOT NULL DEFAULT 0,
        chat_id BIGINT,
        title TEXT,
        last_verified_at TIMESTAMPTZ,
        last_error TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS pairs (
        user_id BIGINT NOT NULL,
        pair_no INTEGER NOT NULL,
        source_input TEXT NOT NULL,
        source_key TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        target_input TEXT NOT NULL,
        target_chat_id BIGINT,
        target_title TEXT,
        scan_count INTEGER,
        last_processed_id BIGINT NOT NULL DEFAULT 0,
        recent_sent_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        forward_rule BOOLEAN NOT NULL DEFAULT FALSE,
        post_rule BOOLEAN NOT NULL DEFAULT TRUE,
        keyword_mode TEXT NOT NULL DEFAULT 'off',
        keyword_values JSONB NOT NULL DEFAULT '[]'::jsonb,
        ads JSONB NOT NULL DEFAULT '[]'::jsonb,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        generation INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, pair_no)
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS runtime_meta (
        key TEXT PRIMARY KEY,
        value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    ''',
]

async def migrate() -> None:
    for sql in MIGRATIONS:
        await execute(sql)
