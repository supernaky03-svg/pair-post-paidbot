from __future__ import annotations

from datetime import datetime, timezone

from app.db.repositories import SettingsRepo, UserRepo
from app.domain.models import PairRecord
from app.telegram.shared_client import client as shared_client


class TargetAdminNotifier:
    def __init__(self) -> None:
        self.settings = SettingsRepo()
        self.users = UserRepo()
        self._settings_key = "target_admin_runtime_notifications"

    async def _session_identity(self) -> tuple[str, str]:
        me = await shared_client.get_me()
        fingerprint = str(getattr(me, "id"))
        username = getattr(me, "username", None)
        if username:
            return fingerprint, f"@{username}"

        full_name = " ".join(
            part for part in [getattr(me, "first_name", None), getattr(me, "last_name", None)] if part
        ).strip()
        return fingerprint, full_name or "session account"

    async def _load_state(self) -> dict:
        return await self.settings.get_json(self._settings_key, {"sent": {}})

    async def _save_state(self, state: dict) -> None:
        await self.settings.set_json(self._settings_key, state)

    def _target_key_for_pair(self, pair: PairRecord) -> str:
        return pair.target_key or pair.target_input

    def _dedupe_key(self, fingerprint: str, pair: PairRecord) -> str:
        return f"{fingerprint}:{pair.user_id}:{self._target_key_for_pair(pair)}"

    async def notify_target_admin_required(self, bot, pair: PairRecord) -> bool:
        fingerprint, account_label = await self._session_identity()
        dedupe_key = self._dedupe_key(fingerprint, pair)

        state = await self._load_state()
        sent = state.setdefault("sent", {})
        if dedupe_key in sent:
            return False

        user = await self.users.get(pair.user_id)
        language = (getattr(user, "language", None) or "en").lower() if user else "en"
        target_label = pair.target_title or pair.target_input

        if language == "my":
            text = (
                "Target မှာ repost လုပ်မရသေးပါ။\n\n"
                f"Target: {target_label}\n"
                f"Target link: {pair.target_input}\n\n"
                f"{account_label} ကို target မှာ admin ပေးပြီး Post Messages / write permission ဖွင့်ပေးပါ။"
            )
        else:
            text = (
                "Reposting to the target is currently blocked.\n\n"
                f"Target: {target_label}\n"
                f"Target link: {pair.target_input}\n\n"
                f"Please give {account_label} admin rights in the target and allow posting/write access."
            )

        await bot.send_message(pair.user_id, text)
        sent[dedupe_key] = {"sent_at": datetime.now(timezone.utc).isoformat()}
        await self._save_state(state)
        return True

    async def clear_for_pair(self, pair: PairRecord) -> None:
        state = await self._load_state()
        sent = state.setdefault("sent", {})
        suffix = f":{pair.user_id}:{self._target_key_for_pair(pair)}"
        changed = False
        for key in list(sent.keys()):
            if key.endswith(suffix):
                sent.pop(key, None)
                changed = True
        if changed:
            await self._save_state(state)
      
