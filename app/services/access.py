from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram.types import User as TgUser

from app.core.config import settings
from app.db.repositories import OtpRepo, PairRepo, UserRepo
from app.i18n.translator import t


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(user_id: int) -> bool:
    return user_id in (settings.admin_ids or [])


class AccessService:
    def __init__(self) -> None:
        self.users = UserRepo()
        self.otps = OtpRepo()
        self.pairs = PairRepo()

    async def ensure_user(self, tg_user: TgUser):
        user = await self.users.ensure(
            tg_user.id,
            tg_user.username,
            " ".join(
                x for x in [tg_user.first_name, tg_user.last_name] if x
            ).strip() or tg_user.first_name,
        )

        # Bootstrap / permanent bypass for env-defined admins.
        # This prevents the "admin needs OTP before being able to create OTP" problem.
        if _is_admin(tg_user.id):
            if user.is_banned:
                await self.users.set_ban(tg_user.id, False)

            needs_activation = (
                user.status != "activated"
                or user.activated_until is None
                or user.activated_until < _utcnow()
                or bool(getattr(user, "needs_restore_choice", False))
            )

            if needs_activation:
                await self.users.activate(
                    tg_user.id,
                    _utcnow() + timedelta(days=3650),  # ~10 years
                    needs_restore_choice=False,
                )

            await self.users.clear_restore_choice(tg_user.id)
            user = await self.users.get(tg_user.id)

        return user

    async def can_use_features(self, user) -> tuple[bool, str | None]:
        # Env-defined admins are always allowed.
        if _is_admin(user.user_id):
            return True, None

        if user.is_banned:
            return False, t(user.language, "access_blocked")

        if user.status != "activated":
            return False, t(user.language, "otp_required")

        return True, None

    async def redeem_otp(self, user_id: int, raw_key: str) -> tuple[str, bool]:
        prior_pairs = await self.pairs.list_for_user(user_id, active_only=False)

        try:
            activated_until = await self.otps.redeem(raw_key, user_id)
        except ValueError as exc:
            if str(exc) == "used":
                return "used", False
            return "invalid", False

        await self.users.activate(
            user_id,
            activated_until,
            needs_restore_choice=bool(prior_pairs),
        )
        return "ok", bool(prior_pairs)
