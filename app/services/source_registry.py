from __future__ import annotations

from datetime import datetime, timezone

from app.db.repositories import PairRepo, SourceRepo
from app.domain.models import PairRecord, SourceRecord
from app.telegram.entity import leave_source, resolve_source


class SourceRegistryService:
    def __init__(self) -> None:
        self.sources = SourceRepo()
        self.pairs = PairRepo()

    async def attach_source(self, pair: PairRecord, resolved) -> SourceRecord:
        all_active = await self.pairs.list_all_active()
        in_use = sum(1 for item in all_active if item.source_key == resolved.source_key)
        source = await self.sources.get(resolved.source_key)
        if not source:
            source = SourceRecord(
                source_key=resolved.source_key,
                source_input=resolved.source_input,
                source_kind=resolved.source_kind,
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
            source.source_input = resolved.source_input
            source.source_kind = resolved.source_kind
            source.normalized_value = resolved.normalized_value
            source.invite_hash = resolved.invite_hash
            source.joined_by_shared_session = resolved.joined_by_shared_session
            source.active_pair_reference_count = max(1, in_use)
            source.chat_id = resolved.chat_id
            source.title = resolved.title
            source.last_verified_at = datetime.now(timezone.utc)
            source.last_error = None
        await self.sources.save(source)
        return source

    async def detach_source_if_unused(self, source_key: str, entity=None) -> bool:
        source = await self.sources.get(source_key)
        if not source:
            return False
        all_active = await self.pairs.list_all_active()
        in_use = sum(1 for item in all_active if item.source_key == source_key)
        source.active_pair_reference_count = in_use
        source.last_verified_at = datetime.now(timezone.utc)
        await self.sources.save(source)
        if in_use == 0 and source.joined_by_shared_session and entity is not None:
            await leave_source(entity)
            source.joined_by_shared_session = False
            await self.sources.save(source)
            return True
        return False

    async def rejoin_private_sources_for_current_session(self) -> list[str]:
        touched: list[str] = []
        all_active = await self.pairs.list_all_active()
        active_keys = {item.source_key for item in all_active}
        for source in await self.sources.list_joined_private():
            if source.source_key not in active_keys:
                continue
            try:
                resolved = await resolve_source(source.source_input)
                source.joined_by_shared_session = resolved.joined_by_shared_session
                source.chat_id = resolved.chat_id
                source.title = resolved.title
                source.last_error = None
                source.last_verified_at = datetime.now(timezone.utc)
                await self.sources.save(source)
                touched.append(source.source_key)
            except Exception as exc:
                source.last_error = str(exc)
                source.last_verified_at = datetime.now(timezone.utc)
                await self.sources.save(source)
        return touched
        
