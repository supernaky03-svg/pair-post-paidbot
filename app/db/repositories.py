from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.connection import execute, fetch_all, fetch_one
from app.domain.models import PairRecord, SourceRecord, TargetRecord, UserRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_otp(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def parse_duration(code: str) -> timedelta:
    code = code.strip().lower()
    if not code:
        raise ValueError("duration required")
    unit = code[-1]
    value = int(code[:-1])
    if unit == "d":
        return timedelta(days=value)
    if unit == "m":
        return timedelta(days=value * 30)
    if unit == "y":
        return timedelta(days=value * 365)
    raise ValueError("unsupported duration")


class UserRepo:
    async def upsert_basic(self, user_id: int, username: str | None, full_name: str | None) -> None:
        await execute(
            '''
            INSERT INTO users (user_id, username, full_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = NOW()
            ''',
            (user_id, username, full_name),
        )

    def _row_to_user(self, row: dict[str, Any]) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            username=row.get("username"),
            full_name=row.get("full_name"),
            language=row.get("language") or settings.language_default,
            status=row.get("status") or "not_activated",
            activated_until=row.get("activated_until"),
            is_banned=bool(row.get("is_banned")),
            pair_limit_override=row.get("pair_limit_override"),
            needs_restore_choice=bool(row.get("needs_restore_choice", False)),
        )

    async def get(self, user_id: int) -> UserRecord | None:
        row = await fetch_one("SELECT * FROM users WHERE user_id = %s", (user_id,))
        return self._row_to_user(row) if row else None

    async def ensure(self, user_id: int, username: str | None, full_name: str | None) -> UserRecord:
        await self.upsert_basic(user_id, username, full_name)
        row = await self.get(user_id)
        assert row is not None
        if row.status == "activated" and row.activated_until and row.activated_until < _utcnow():
            await self.mark_expired(user_id)
            row.status = "expired"
        return row

    async def set_language(self, user_id: int, language: str) -> None:
        await execute(
            "UPDATE users SET language = %s, updated_at = NOW() WHERE user_id = %s",
            (language, user_id),
        )

    async def set_ban(self, user_id: int, value: bool) -> None:
        if value:
            await execute(
                "UPDATE users SET is_banned = TRUE, status = 'banned', updated_at = NOW() WHERE user_id = %s",
                (user_id,),
            )
            return
        await execute(
            """
            UPDATE users
            SET is_banned = FALSE,
                status = CASE WHEN activated_until > NOW() THEN 'activated' ELSE 'expired' END,
                updated_at = NOW()
            WHERE user_id = %s
            """,
            (user_id,),
        )

    async def clear_restore_choice(self, user_id: int) -> None:
        await execute(
            "UPDATE users SET needs_restore_choice = FALSE, updated_at = NOW() WHERE user_id = %s",
            (user_id,),
        )

    async def activate(self, user_id: int, until: datetime, *, needs_restore_choice: bool) -> None:
        await execute(
            """
            UPDATE users
            SET status = 'activated',
                activated_until = %s,
                needs_restore_choice = %s,
                updated_at = NOW()
            WHERE user_id = %s
            """,
            (until, needs_restore_choice, user_id),
        )

    async def mark_expired(self, user_id: int) -> None:
        await execute(
            "UPDATE users SET status = 'expired', updated_at = NOW() WHERE user_id = %s",
            (user_id,),
        )

    async def list_active_non_banned(self) -> list[UserRecord]:
        rows = await fetch_all(
            "SELECT * FROM users WHERE status = 'activated' AND is_banned = FALSE ORDER BY user_id"
        )
        return [self._row_to_user(r) for r in rows]

    async def list_expired(self) -> list[UserRecord]:
        rows = await fetch_all(
            "SELECT * FROM users WHERE status = 'expired' ORDER BY user_id"
        )
        return [self._row_to_user(r) for r in rows]

    async def set_pair_limit(self, user_id: int, value: int | None) -> None:
        await execute(
            "UPDATE users SET pair_limit_override = %s, updated_at = NOW() WHERE user_id = %s",
            (value, user_id),
        )

    async def reset_user_setup(self, user_id: int) -> None:
        await execute(
            "UPDATE pairs SET active = FALSE, updated_at = NOW() WHERE user_id = %s",
            (user_id,),
        )
        await execute(
            "UPDATE users SET needs_restore_choice = FALSE, updated_at = NOW() WHERE user_id = %s",
            (user_id,),
        )


class OtpRepo:
    async def create(self, duration_code: str, raw_key: str, admin_id: int) -> None:
        parse_duration(duration_code)
        await execute(
            '''
            INSERT INTO otp_keys (key_hash, duration_code, created_by_admin)
            VALUES (%s, %s, %s)
            ON CONFLICT (key_hash) DO UPDATE SET
                duration_code = EXCLUDED.duration_code,
                created_by_admin = EXCLUDED.created_by_admin
            ''',
            (hash_otp(raw_key), duration_code, admin_id),
        )

    async def get_by_raw(self, raw_key: str) -> dict[str, Any] | None:
        return await fetch_one("SELECT * FROM otp_keys WHERE key_hash = %s", (hash_otp(raw_key),))

    async def redeem(self, raw_key: str, user_id: int) -> datetime:
        row = await self.get_by_raw(raw_key)
        if not row:
            raise ValueError("invalid")
        if row["is_used"]:
            raise ValueError("used")
        duration = parse_duration(row["duration_code"])
        activated_until = _utcnow() + duration
        await execute(
            '''
            UPDATE otp_keys
            SET is_used = TRUE,
                redeemed_by_user_id = %s,
                redeemed_at = NOW(),
                activated_until = %s
            WHERE key_hash = %s
            ''',
            (user_id, activated_until, hash_otp(raw_key)),
        )
        return activated_until


class PairRepo:
    def _row_to_pair(self, row: dict[str, Any]) -> PairRecord:
        recent = row.get("recent_sent_ids") or []
        if isinstance(recent, str):
            recent = json.loads(recent)
        keywords = row.get("keyword_values") or []
        if isinstance(keywords, str):
            keywords = json.loads(keywords)
        ads = row.get("ads") or []
        if isinstance(ads, str):
            ads = json.loads(ads)
        return PairRecord(
            user_id=row["user_id"],
            pair_no=row["pair_no"],
            source_input=row["source_input"],
            source_key=row["source_key"],
            source_kind=row["source_kind"],
            target_input=row["target_input"],
            target_key=row.get("target_key"),
            target_chat_id=row.get("target_chat_id"),
            target_title=row.get("target_title"),
            scan_count=row.get("scan_count"),
            last_processed_id=row.get("last_processed_id") or 0,
            recent_sent_ids=list(recent),
            forward_rule=bool(row.get("forward_rule")),
            remove_url_rule=bool(row.get("remove_url_rule", True)),
            post_rule=bool(row.get("post_rule")),
            keyword_mode=row.get("keyword_mode") or "off",
            keyword_values=list(keywords),
            ads=list(ads),
            active=bool(row.get("active", True)),
            generation=row.get("generation") or 1,
        )

    async def list_for_user(self, user_id: int, *, active_only: bool = True) -> list[PairRecord]:
        sql = "SELECT * FROM pairs WHERE user_id = %s"
        if active_only:
            sql += " AND active = TRUE"
        sql += " ORDER BY pair_no"
        rows = await fetch_all(sql, (user_id,))
        return [self._row_to_pair(r) for r in rows]

    async def list_all_active(self) -> list[PairRecord]:
        rows = await fetch_all("SELECT * FROM pairs WHERE active = TRUE ORDER BY user_id, pair_no")
        return [self._row_to_pair(r) for r in rows]

    async def get(self, user_id: int, pair_no: int) -> PairRecord | None:
        row = await fetch_one(
            "SELECT * FROM pairs WHERE user_id = %s AND pair_no = %s ORDER BY active DESC LIMIT 1",
            (user_id, pair_no),
        )
        return self._row_to_pair(row) if row else None

    async def save(self, pair: PairRecord) -> None:
        await execute(
            '''
            INSERT INTO pairs (
                user_id, pair_no, source_input, source_key, source_kind, target_input, target_key,
                target_chat_id, target_title, scan_count, last_processed_id, recent_sent_ids,
                forward_rule, remove_url_rule, post_rule, keyword_mode, keyword_values, ads, active, generation, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, NOW())
            ON CONFLICT (user_id, pair_no) DO UPDATE SET
                source_input = EXCLUDED.source_input,
                source_key = EXCLUDED.source_key,
                source_kind = EXCLUDED.source_kind,
                target_input = EXCLUDED.target_input,
                target_key = EXCLUDED.target_key,
                target_chat_id = EXCLUDED.target_chat_id,
                target_title = EXCLUDED.target_title,
                scan_count = EXCLUDED.scan_count,
                last_processed_id = EXCLUDED.last_processed_id,
                recent_sent_ids = EXCLUDED.recent_sent_ids,
                forward_rule = EXCLUDED.forward_rule,
                remove_url_rule = EXCLUDED.remove_url_rule,
                post_rule = EXCLUDED.post_rule,
                keyword_mode = EXCLUDED.keyword_mode,
                keyword_values = EXCLUDED.keyword_values,
                ads = EXCLUDED.ads,
                active = EXCLUDED.active,
                generation = EXCLUDED.generation,
                updated_at = NOW()
            ''',
            (
                pair.user_id,
                pair.pair_no,
                pair.source_input,
                pair.source_key,
                pair.source_kind,
                pair.target_input,
                pair.target_key,
                pair.target_chat_id,
                pair.target_title,
                pair.scan_count,
                pair.last_processed_id,
                json.dumps(pair.recent_sent_ids[-settings.recent_ids_limit :]),
                pair.forward_rule,
                pair.remove_url_rule,
                pair.post_rule,
                pair.keyword_mode,
                json.dumps(pair.keyword_values),
                json.dumps(pair.ads),
                pair.active,
                pair.generation,
            ),
        )

    async def deactivate(self, user_id: int, pair_no: int) -> None:
        await execute(
            "UPDATE pairs SET active = FALSE, updated_at = NOW() WHERE user_id = %s AND pair_no = %s",
            (user_id, pair_no),
        )

    async def mark_all_inactive_for_user(self, user_id: int) -> None:
        await execute(
            "UPDATE pairs SET active = FALSE, updated_at = NOW() WHERE user_id = %s",
            (user_id,),
        )


class SourceRepo:
    def _row_to_source(self, row: dict[str, Any]) -> SourceRecord:
        return SourceRecord(
            source_key=row["source_key"],
            source_input=row["source_input"],
            source_kind=row["source_kind"],
            normalized_value=row["normalized_value"],
            invite_hash=row.get("invite_hash"),
            joined_by_shared_session=bool(row.get("joined_by_shared_session")),
            active_pair_reference_count=row.get("active_pair_reference_count") or 0,
            chat_id=row.get("chat_id"),
            title=row.get("title"),
            last_verified_at=row.get("last_verified_at"),
            last_error=row.get("last_error"),
        )

    async def get(self, source_key: str) -> SourceRecord | None:
        row = await fetch_one("SELECT * FROM sources WHERE source_key = %s", (source_key,))
        return self._row_to_source(row) if row else None

    async def list_all(self) -> list[SourceRecord]:
        rows = await fetch_all("SELECT * FROM sources ORDER BY source_kind, source_input")
        return [self._row_to_source(r) for r in rows]

    async def list_joined_private(self) -> list[SourceRecord]:
        rows = await fetch_all(
            "SELECT * FROM sources WHERE joined_by_shared_session = TRUE ORDER BY source_input"
        )
        return [self._row_to_source(r) for r in rows]

    async def save(self, source: SourceRecord) -> None:
        await execute(
            '''
            INSERT INTO sources (
                source_key, source_input, source_kind, normalized_value, invite_hash,
                joined_by_shared_session, active_pair_reference_count, chat_id, title,
                last_verified_at, last_error, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (source_key) DO UPDATE SET
                source_input = EXCLUDED.source_input,
                source_kind = EXCLUDED.source_kind,
                normalized_value = EXCLUDED.normalized_value,
                invite_hash = EXCLUDED.invite_hash,
                joined_by_shared_session = EXCLUDED.joined_by_shared_session,
                active_pair_reference_count = EXCLUDED.active_pair_reference_count,
                chat_id = EXCLUDED.chat_id,
                title = EXCLUDED.title,
                last_verified_at = EXCLUDED.last_verified_at,
                last_error = EXCLUDED.last_error,
                updated_at = NOW()
            ''',
            (
                source.source_key,
                source.source_input,
                source.source_kind,
                source.normalized_value,
                source.invite_hash,
                source.joined_by_shared_session,
                source.active_pair_reference_count,
                source.chat_id,
                source.title,
                source.last_verified_at,
                source.last_error,
            ),
        )


class TargetRepo:
    def _row_to_target(self, row: dict[str, Any]) -> TargetRecord:
        return TargetRecord(
            target_key=row["target_key"],
            target_input=row["target_input"],
            target_kind=row["target_kind"],
            normalized_value=row["normalized_value"],
            invite_hash=row.get("invite_hash"),
            joined_by_shared_session=bool(row.get("joined_by_shared_session")),
            active_pair_reference_count=row.get("active_pair_reference_count") or 0,
            chat_id=row.get("chat_id"),
            title=row.get("title"),
            last_verified_at=row.get("last_verified_at"),
            last_error=row.get("last_error"),
            last_session_fingerprint=row.get("last_session_fingerprint"),
        )

    async def get(self, target_key: str) -> TargetRecord | None:
        row = await fetch_one("SELECT * FROM targets WHERE target_key = %s", (target_key,))
        return self._row_to_target(row) if row else None

    async def list_all(self) -> list[TargetRecord]:
        rows = await fetch_all("SELECT * FROM targets ORDER BY target_kind, target_input")
        return [self._row_to_target(r) for r in rows]

    async def save(self, target: TargetRecord) -> None:
        await execute(
            """
            INSERT INTO targets (
                target_key, target_input, target_kind, normalized_value, invite_hash,
                joined_by_shared_session, active_pair_reference_count, chat_id, title,
                last_verified_at, last_error, last_session_fingerprint, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (target_key) DO UPDATE SET
                target_input = EXCLUDED.target_input,
                target_kind = EXCLUDED.target_kind,
                normalized_value = EXCLUDED.normalized_value,
                invite_hash = EXCLUDED.invite_hash,
                joined_by_shared_session = EXCLUDED.joined_by_shared_session,
                active_pair_reference_count = EXCLUDED.active_pair_reference_count,
                chat_id = EXCLUDED.chat_id,
                title = EXCLUDED.title,
                last_verified_at = EXCLUDED.last_verified_at,
                last_error = EXCLUDED.last_error,
                last_session_fingerprint = EXCLUDED.last_session_fingerprint,
                updated_at = NOW()
            """,
            (
                target.target_key,
                target.target_input,
                target.target_kind,
                target.normalized_value,
                target.invite_hash,
                target.joined_by_shared_session,
                target.active_pair_reference_count,
                target.chat_id,
                target.title,
                target.last_verified_at,
                target.last_error,
                target.last_session_fingerprint,
            ),
        )


class SettingsRepo:
    async def get_json(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        row = await fetch_one("SELECT value_json FROM global_settings WHERE key = %s", (key,))
        return row["value_json"] if row else (default or {})

    async def set_json(self, key: str, value: dict[str, Any]) -> None:
        await execute(
            '''
            INSERT INTO global_settings (key, value_json, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()
            ''',
            (key, json.dumps(value)),
        )
        
