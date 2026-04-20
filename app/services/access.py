from __future__ import annotations

from aiogram.types import User as TgUser

from app.db.repositories import OtpRepo, PairRepo, UserRepo
from app.i18n.translator import t

class AccessService:
    def __init__(self) -> None:
        self.users = UserRepo()
        self.otps = OtpRepo()
        self.pairs = PairRepo()

    async def ensure_user(self, tg_user: TgUser):
        return await self.users.ensure(
            tg_user.id,
            tg_user.username,
            " ".join(x for x in [tg_user.first_name, tg_user.last_name] if x).strip() or tg_user.first_name,
        )

    async def can_use_features(self, user) -> tuple[bool, str | None]:
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
        await self.users.activate(user_id, activated_until, needs_restore_choice=bool(prior_pairs))
        return "ok", bool(prior_pairs)

