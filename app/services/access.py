
from __future__ import annotations

from dataclasses import dataclass

from ..core.runtime import cache_user, clear_user_pairs, get_runtime
from ..db.repositories import Repository
from ..models import UserRecord, utc_now
from ..utils.parsing import apply_duration


@dataclass(slots=True)
class OTPRedeemResult:
    ok: bool
    user: UserRecord | None = None
    expiry: object | None = None
    needs_restore_choice: bool = False
    message_key: str = "invalid_otp"


async def ensure_user_profile(telegram_user) -> UserRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    user = await repo.upsert_user(telegram_user.id, telegram_user.username)
    cache_user(user)
    return user


async def redeem_otp(user: UserRecord, key: str) -> OTPRedeemResult:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    otp = await repo.get_otp(key)
    if not otp or otp.is_used:
        return OTPRedeemResult(ok=False, user=user, message_key="invalid_otp")
    expiry = apply_duration(utc_now(), otp.duration_value, otp.duration_unit)
    await repo.mark_otp_used(key, user.telegram_user_id)
    user = await repo.update_user_access(user.telegram_user_id, expiry, otp.key)
    cache_user(user)
    had_previous_data = bool(user.database_channel_id or runtime.pairs_by_user.get(user.telegram_user_id))
    return OTPRedeemResult(
        ok=True,
        user=user,
        expiry=expiry,
        needs_restore_choice=had_previous_data,
        message_key="otp_success",
    )


async def apply_restore_choice(user: UserRecord, mode: str) -> UserRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    if mode == "reuse":
        user = await repo.update_user_restore_mode(user.telegram_user_id, "reuse")
        cache_user(user)
        return user
    next_version = int(user.reset_version) + 1
    user = await repo.update_user_restore_mode(
        user.telegram_user_id,
        "reset",
        reset_version=next_version,
        reset_at=utc_now(),
        clear_database_channel=True,
    )
    await repo.delete_all_pairs_for_user(user.telegram_user_id)
    clear_user_pairs(user.telegram_user_id)
    cache_user(user)
    return user
