
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, List, Optional

from ..models import OTPRecord, PairRecord, UserRecord, utc_now
from .database import Database


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert_user(self, user_id: int, username: str | None) -> UserRecord:
        row = await self.db.fetchrow(
            """
            INSERT INTO users (telegram_user_id, username)
            VALUES (%s, %s)
            ON CONFLICT (telegram_user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                updated_at = NOW()
            RETURNING *
            """,
            [int(user_id), username],
        )
        return UserRecord.from_row(row)

    async def get_user(self, user_id: int) -> UserRecord | None:
        row = await self.db.fetchrow(
            "SELECT * FROM users WHERE telegram_user_id = %s",
            [int(user_id)],
        )
        return UserRecord.from_row(row) if row else None

    async def list_users(self) -> List[UserRecord]:
        rows = await self.db.fetch("SELECT * FROM users ORDER BY telegram_user_id ASC")
        return [UserRecord.from_row(row) for row in rows]

    async def update_user_language(self, user_id: int, language: str) -> UserRecord:
        row = await self.db.fetchrow(
            """
            UPDATE users
            SET language = %s, updated_at = NOW()
            WHERE telegram_user_id = %s
            RETURNING *
            """,
            [language, int(user_id)],
        )
        return UserRecord.from_row(row)

    async def update_user_database_channel(
        self,
        user_id: int,
        channel_id: int,
        channel_link: str,
    ) -> UserRecord:
        row = await self.db.fetchrow(
            """
            UPDATE users
            SET
                database_channel_id = %s,
                database_channel_link = %s,
                updated_at = NOW()
            WHERE telegram_user_id = %s
            RETURNING *
            """,
            [int(channel_id), channel_link, int(user_id)],
        )
        return UserRecord.from_row(row)

    async def update_user_access(
        self,
        user_id: int,
        access_expires_at: datetime,
        otp_key: str,
    ) -> UserRecord:
        row = await self.db.fetchrow(
            """
            UPDATE users
            SET
                access_expires_at = %s,
                last_otp_used = %s,
                updated_at = NOW()
            WHERE telegram_user_id = %s
            RETURNING *
            """,
            [access_expires_at, otp_key, int(user_id)],
        )
        return UserRecord.from_row(row)

    async def update_user_restore_mode(
        self,
        user_id: int,
        restore_mode: str,
        *,
        reset_version: int | None = None,
        reset_at: datetime | None = None,
        clear_database_channel: bool = False,
    ) -> UserRecord:
        assignments = ["restore_mode = %s", "updated_at = NOW()"]
        params: list = [restore_mode]
        if reset_version is not None:
            assignments.append("reset_version = %s")
            params.append(int(reset_version))
        if reset_at is not None:
            assignments.append("reset_at = %s")
            params.append(reset_at)
        if clear_database_channel:
            assignments.append("database_channel_id = NULL")
            assignments.append("database_channel_link = NULL")
        params.append(int(user_id))
        row = await self.db.fetchrow(
            f"""
            UPDATE users
            SET {", ".join(assignments)}
            WHERE telegram_user_id = %s
            RETURNING *
            """,
            params,
        )
        return UserRecord.from_row(row)

    async def set_user_ban_state(self, user_id: int, is_banned: bool) -> UserRecord | None:
        row = await self.db.fetchrow(
            """
            UPDATE users
            SET is_banned = %s, updated_at = NOW()
            WHERE telegram_user_id = %s
            RETURNING *
            """,
            [bool(is_banned), int(user_id)],
        )
        return UserRecord.from_row(row) if row else None

    async def set_user_pair_limit(self, user_id: int, pair_limit: int | None) -> UserRecord:
        row = await self.db.fetchrow(
            """
            UPDATE users
            SET pair_limit = %s, updated_at = NOW()
            WHERE telegram_user_id = %s
            RETURNING *
            """,
            [pair_limit, int(user_id)],
        )
        return UserRecord.from_row(row)

    async def create_otp(
        self,
        *,
        key: str,
        duration_value: int,
        duration_unit: str,
        created_by_admin: int,
    ) -> OTPRecord:
        row = await self.db.fetchrow(
            """
            INSERT INTO otp_keys (
                key,
                duration_value,
                duration_unit,
                created_by_admin
            )
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            [key, int(duration_value), duration_unit, int(created_by_admin)],
        )
        return OTPRecord.from_row(row)

    async def get_otp(self, key: str) -> OTPRecord | None:
        row = await self.db.fetchrow(
            "SELECT * FROM otp_keys WHERE key = %s",
            [key],
        )
        return OTPRecord.from_row(row) if row else None

    async def mark_otp_used(self, key: str, user_id: int) -> OTPRecord:
        row = await self.db.fetchrow(
            """
            UPDATE otp_keys
            SET
                is_used = TRUE,
                used_by_user_id = %s,
                used_at = NOW()
            WHERE key = %s
            RETURNING *
            """,
            [int(user_id), key],
        )
        return OTPRecord.from_row(row)

    async def list_pairs(self, user_id: int | None = None) -> List[PairRecord]:
        params: list = []
        where = ""
        if user_id is not None:
            where = "WHERE owner_user_id = %s"
            params.append(int(user_id))
        rows = await self.db.fetch(
            f"SELECT * FROM user_pairs {where} ORDER BY owner_user_id, pair_id",
            params,
        )
        return [self._row_to_pair(row) for row in rows]

    async def count_pairs(self, user_id: int) -> int:
        row = await self.db.fetchrow(
            "SELECT COUNT(*) AS total FROM user_pairs WHERE owner_user_id = %s",
            [int(user_id)],
        )
        return int(row["total"]) if row else 0

    async def get_pair(self, user_id: int, pair_id: int) -> PairRecord | None:
        row = await self.db.fetchrow(
            """
            SELECT * FROM user_pairs
            WHERE owner_user_id = %s AND pair_id = %s
            """,
            [int(user_id), int(pair_id)],
        )
        return self._row_to_pair(row) if row else None

    async def upsert_pair(self, pair: PairRecord) -> PairRecord:
        row = await self.db.fetchrow(
            """
            INSERT INTO user_pairs (
                owner_user_id,
                pair_id,
                source_id,
                target_id,
                source_chat_id,
                target_chat_id,
                last_processed_id,
                recent_sent_ids,
                forward_rule,
                post_rule,
                scan_amount,
                ads_links,
                ban_keywords,
                post_keywords
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb
            )
            ON CONFLICT (owner_user_id, pair_id)
            DO UPDATE SET
                source_id = EXCLUDED.source_id,
                target_id = EXCLUDED.target_id,
                source_chat_id = EXCLUDED.source_chat_id,
                target_chat_id = EXCLUDED.target_chat_id,
                last_processed_id = EXCLUDED.last_processed_id,
                recent_sent_ids = EXCLUDED.recent_sent_ids,
                forward_rule = EXCLUDED.forward_rule,
                post_rule = EXCLUDED.post_rule,
                scan_amount = EXCLUDED.scan_amount,
                ads_links = EXCLUDED.ads_links,
                ban_keywords = EXCLUDED.ban_keywords,
                post_keywords = EXCLUDED.post_keywords,
                updated_at = NOW()
            RETURNING *
            """,
            [
                pair.owner_user_id,
                pair.pair_id,
                pair.source_id,
                pair.target_id,
                pair.source_chat_id,
                pair.target_chat_id,
                pair.last_processed_id,
                json.dumps(pair.recent_sent_ids),
                pair.forward_rule,
                pair.post_rule,
                pair.scan_amount,
                json.dumps(pair.ads_links),
                json.dumps(pair.ban_keywords),
                json.dumps(pair.post_keywords),
            ],
        )
        return self._row_to_pair(row)

    async def delete_pair(self, user_id: int, pair_id: int) -> None:
        await self.db.execute(
            "DELETE FROM user_pairs WHERE owner_user_id = %s AND pair_id = %s",
            [int(user_id), int(pair_id)],
        )

    async def delete_all_pairs_for_user(self, user_id: int) -> None:
        await self.db.execute(
            "DELETE FROM user_pairs WHERE owner_user_id = %s",
            [int(user_id)],
        )

    async def set_global_pair_limit(self, value: int) -> int:
        await self.db.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES ('default_pair_limit', %s, NOW())
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            [str(int(value))],
        )
        return int(value)

    async def get_global_pair_limit(self, default: int) -> int:
        row = await self.db.fetchrow(
            "SELECT value FROM app_settings WHERE key = 'default_pair_limit'"
        )
        if not row:
            return int(default)
        try:
            return int(row["value"])
        except Exception:
            return int(default)

    async def log_admin_action(self, admin_user_id: int, action: str, details: str) -> None:
        await self.db.execute(
            """
            INSERT INTO admin_logs (admin_user_id, action, details)
            VALUES (%s, %s, %s)
            """,
            [int(admin_user_id), action, details],
        )

    def _row_to_pair(self, row: dict) -> PairRecord:
        row = dict(row)
        for key in ("recent_sent_ids", "ads_links", "ban_keywords", "post_keywords"):
            value = row.get(key)
            if isinstance(value, str):
                try:
                    row[key] = json.loads(value)
                except Exception:
                    row[key] = []
            elif value is None:
                row[key] = []
        return PairRecord.from_row(row)
