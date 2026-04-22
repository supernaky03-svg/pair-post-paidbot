from __future__ import annotations

from collections import defaultdict

from app.db.repositories import PairRepo, SettingsRepo, UserRepo
from app.i18n.translator import t
from app.services.source_registry import SourceRegistryService
from app.services.target_registry import TargetRegistryService
from app.telegram.shared_client import client as shared_client


class SessionReconcileService:
    def __init__(self) -> None:
        self.settings = SettingsRepo()
        self.pairs = PairRepo()
        self.users = UserRepo()
        self.sources = SourceRegistryService()
        self.targets = TargetRegistryService()

    async def _current_session_info(self) -> tuple[str, str]:
        me = await shared_client.get_me()
        fingerprint = str(getattr(me, "id"))
        username = getattr(me, "username", None)
        if username:
            return fingerprint, f"@{username}"
        full_name = " ".join(
            part for part in [getattr(me, "first_name", None), getattr(me, "last_name", None)] if part
        ).strip()
        return fingerprint, full_name or "session account"

    async def _notify_users(self, bot, account_label: str) -> None:
        pairs = await self.pairs.list_all_active()
        targets_by_user: dict[int, list[str]] = defaultdict(list)
        seen: dict[int, set[str]] = defaultdict(set)

        for pair in pairs:
            label = pair.target_title or pair.target_input
            if label not in seen[pair.user_id]:
                seen[pair.user_id].add(label)
                targets_by_user[pair.user_id].append(label)

        for user_id, targets in targets_by_user.items():
            user = await self.users.get(user_id)
            language = (getattr(user, "language", None) or "en").lower() if user else "en"
            if language == "my":
                text = (
                    "Repost account ပြောင်းသွားပါပြီ။\n\n"
                    f"Target တွေမှာ {account_label} ကို admin ပေးပါ။\n\n"
                    "Targets:\n- " + "\n- ".join(targets)
                )
            else:
                text = (
                    "The repost account has changed.\n\n"
                    f"Please give {account_label} admin rights in these targets:\n\n"
                    "- " + "\n- ".join(targets)
                )
            try:
                await bot.send_message(user_id, text)
            except Exception:
                continue

    async def run(self, bot) -> None:
        fingerprint, account_label = await self._current_session_info()
        saved = await self.settings.get_json("shared_session_identity", {})
        previous_fingerprint = str(saved.get("fingerprint") or "")
        changed = bool(previous_fingerprint) and previous_fingerprint != fingerprint

        if changed:
            await self.sources.rejoin_private_sources_for_current_session()
            await self.targets.reconcile_targets_for_current_session(fingerprint)
            await self._notify_users(bot, account_label)

        await self.settings.set_json(
            "shared_session_identity",
            {"fingerprint": fingerprint, "label": account_label},
        )
      
