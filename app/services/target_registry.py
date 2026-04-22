from __future__ import annotations

from datetime import datetime, timezone

from app.db.repositories import PairRepo, TargetRepo
from app.domain.models import PairRecord, TargetRecord
from app.telegram.entity import (
    describe_target,
    leave_target,
    resolve_and_join_target,
    resolve_target,
)
from app.telegram.shared_client import client as shared_client


class TargetRegistryService:
    def __init__(self) -> None:
        self.targets = TargetRepo()
        self.pairs = PairRepo()

    def _pair_target_key(self, pair: PairRecord) -> str | None:
        if pair.target_key:
            return pair.target_key
        try:
            return describe_target(pair.target_input).target_key
        except Exception:
            return None

    async def attach_target(self, pair: PairRecord, resolved) -> TargetRecord:
        all_active = await self.pairs.list_all_active()
        in_use = sum(1 for item in all_active if self._pair_target_key(item) == resolved.target_key)
        target = await self.targets.get(resolved.target_key)
        if not target:
            target = TargetRecord(
                target_key=resolved.target_key,
                target_input=resolved.target_input,
                target_kind=resolved.target_kind,
                normalized_value=resolved.normalized_value,
                invite_hash=resolved.invite_hash,
                joined_by_shared_session=resolved.joined_by_shared_session,
                active_pair_reference_count=max(1, in_use),
                chat_id=resolved.chat_id,
                title=resolved.title,
                last_verified_at=datetime.now(timezone.utc),
                last_error=None,
            )
        else:
            target.target_input = resolved.target_input
            target.target_kind = resolved.target_kind
            target.normalized_value = resolved.normalized_value
            target.invite_hash = resolved.invite_hash
            target.joined_by_shared_session = resolved.joined_by_shared_session
            target.active_pair_reference_count = max(1, in_use)
            target.chat_id = resolved.chat_id
            target.title = resolved.title
            target.last_verified_at = datetime.now(timezone.utc)
            target.last_error = None
        await self.targets.save(target)
        return target

    async def detach_target_if_unused(self, target_key: str, entity=None) -> bool:
        target = await self.targets.get(target_key)
        if not target:
            return False
        all_active = await self.pairs.list_all_active()
        in_use = sum(1 for item in all_active if self._pair_target_key(item) == target_key)
        target.active_pair_reference_count = in_use
        target.last_verified_at = datetime.now(timezone.utc)
        await self.targets.save(target)
        if in_use == 0 and target.joined_by_shared_session and entity is not None:
            await leave_target(entity)
            target.joined_by_shared_session = False
            await self.targets.save(target)
            return True
        return False

    async def cleanup_temporary_target(self, target_input: str, committed_keys: set[str] | None = None) -> None:
        committed_keys = committed_keys or set()
        ref = describe_target(target_input)
        if ref.target_key in committed_keys:
            return
        all_active = await self.pairs.list_all_active()
        if any(self._pair_target_key(item) == ref.target_key for item in all_active):
            return
        try:
            entity = await resolve_target(target_input)
        except Exception:
            return
        await leave_target(entity)

    async def reconcile_targets_for_current_session(self, session_fingerprint: str) -> list[TargetRecord]:
        all_active = await self.pairs.list_all_active()
        unique: dict[str, str] = {}
        for pair in all_active:
            ref = describe_target(pair.target_input)
            unique.setdefault(ref.target_key, pair.target_input)
            if pair.target_key != ref.target_key:
                pair.target_key = ref.target_key
                await self.pairs.save(pair)

        touched: list[TargetRecord] = []
        for target_key, target_input in unique.items():
            try:
                resolved = await resolve_and_join_target(target_input)
                target = await self.targets.get(target_key)
                if not target:
                    target = TargetRecord(
                        target_key=resolved.target_key,
                        target_input=resolved.target_input,
                        target_kind=resolved.target_kind,
                        normalized_value=resolved.normalized_value,
                        invite_hash=resolved.invite_hash,
                    )
                target.target_input = resolved.target_input
                target.target_kind = resolved.target_kind
                target.normalized_value = resolved.normalized_value
                target.invite_hash = resolved.invite_hash
                target.joined_by_shared_session = resolved.joined_by_shared_session
                target.active_pair_reference_count = sum(
                    1 for item in all_active if self._pair_target_key(item) == target_key
                )
                target.chat_id = resolved.chat_id
                target.title = resolved.title
                target.last_verified_at = datetime.now(timezone.utc)
                target.last_error = None
                target.last_session_fingerprint = session_fingerprint
                await self.targets.save(target)
                touched.append(target)
            except Exception as exc:
                target = await self.targets.get(target_key)
                if not target:
                    ref = describe_target(target_input)
                    target = TargetRecord(
                        target_key=ref.target_key,
                        target_input=ref.target_input,
                        target_kind=ref.target_kind,
                        normalized_value=ref.normalized_value,
                        invite_hash=ref.invite_hash,
                    )
                target.active_pair_reference_count = sum(
                    1 for item in all_active if self._pair_target_key(item) == target_key
                )
                target.last_verified_at = datetime.now(timezone.utc)
                target.last_error = str(exc)
                target.last_session_fingerprint = session_fingerprint
                await self.targets.save(target)
                touched.append(target)
        return touched

    async def session_account_label(self) -> str:
        me = await shared_client.get_me()
        username = getattr(me, "username", None)
        if username:
            return f"@{username}"
        full_name = " ".join(
            part for part in [getattr(me, "first_name", None), getattr(me, "last_name", None)] if part
        ).strip()
        return full_name or "session account"
      
