from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telethon.errors.rpcerrorlist import ChatWriteForbiddenError

from app.core.logging import logger
from app.db.repositories import AdsPairRepo, PairRepo
from app.domain.models import AdsPairRecord, PairRecord
from app.services.repost_logic import (
    collect_grouped_messages,
    is_duplicate,
    is_video_message,
    runtime_cache,
    send_ads_pair_album,
    send_ads_pair_single,
    send_album,
    send_single,
    should_process_album,
    should_process_single,
)
from app.services.target_admin_notifier import TargetAdminNotifier
from app.telegram.entity import resolve_and_join_target, resolve_source
from app.telegram.safe_ops import safe_get_messages
from app.telegram.shared_client import client


class RuntimeManager:
    def __init__(self) -> None:
        self.pairs = PairRepo()
        self.ads_pairs = AdsPairRepo()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._active_checks: dict[str, int] = defaultdict(int)
        self._bot = None
        self.notifier = TargetAdminNotifier()

    async def start(self, bot=None) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._bot = bot
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    def clear_cache(self) -> None:
        runtime_cache.clear_all()

    def runtime_warning(self) -> str | None:
        if not client.is_connected():
            return "Shared session is not connected."
        return None

    async def _loop(self) -> None:
        from app.core.config import settings

        while not self._stop.is_set():
            try:
                await self.scan_all_pairs()
            except Exception:
                logger.exception("Runtime scan cycle failed")

            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=settings.poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def scan_all_pairs(self) -> None:
        pairs = await self.pairs.list_all_active()
        for pair in pairs:
            try:
                await self.scan_pair(pair)
            except ChatWriteForbiddenError:
                await self._notify_target_admin_required(pair)
                logger.exception(
                    "Runtime scan failed for pair user_id=%s pair_no=%s source=%s target=%s",
                    pair.user_id,
                    pair.pair_no,
                    pair.source_input,
                    pair.target_input,
                )
            except Exception:
                logger.exception(
                    "Runtime scan failed for pair user_id=%s pair_no=%s source=%s target=%s",
                    pair.user_id,
                    pair.pair_no,
                    pair.source_input,
                    pair.target_input,
                )

        ads_pairs = await self.ads_pairs.list_all_active()
        for pair in ads_pairs:
            try:
                await self.scan_ads_pair(pair)
            except Exception:
                logger.exception(
                    "Ads pair scan failed for user_id=%s pair_no=%s source=%s target=%s",
                    pair.user_id,
                    pair.pair_no,
                    pair.source_input,
                    pair.target_input,
                )
                
    async def _ensure_entities(self, pair: PairRecord):
        cache = runtime_cache.get_pair_entities(pair.user_id, pair.pair_no)
        
        if cache["source"] is None:
            cache["source"] = (await resolve_source(pair.source_input)).entity
            
        if cache["target"] is None:
            cache["target"] = (await resolve_and_join_target(pair.target_input)).entity
            
        return cache["source"], cache["target"]

    async def _ensure_ads_entities(self, pair: AdsPairRecord):
        cache = runtime_cache.get_ads_pair_entities(pair.user_id, pair.pair_no)

        if cache["source"] is None:
            cache["source"] = (await resolve_source(pair.source_input)).entity

        if cache["target"] is None:
            cache["target"] = (await resolve_and_join_target(pair.target_input)).entity

        return cache["source"], cache["target"]

    async def _collect_ads_messages(self, pair: AdsPairRecord, source_entity):
        last_id = int(pair.last_processed_id or 0)
        if last_id == 0:
            if pair.scan_count <= 0:
                latest = await safe_get_messages(source_entity, limit=1)
                if latest:
                    latest_msg = latest[0] if isinstance(latest, list) else latest
                    pair.last_processed_id = int(latest_msg.id)
                    await self.ads_pairs.save(pair)
                return []
            latest = await safe_get_messages(source_entity, limit=pair.scan_count)
            return sorted([m for m in latest], key=lambda x: x.id)

        msgs = []
        async for msg in client.iter_messages(
            source_entity,
            min_id=last_id,
            reverse=True,
        ):
            msgs.append(msg)
        return msgs

    def _ads_pair_due(self, pair: AdsPairRecord) -> bool:
        if pair.next_send_at is None:
            return True
        next_send_at = pair.next_send_at
        if next_send_at.tzinfo is None:
            next_send_at = next_send_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= next_send_at

    async def scan_ads_pair(self, pair: AdsPairRecord) -> None:
        if not self._ads_pair_due(pair):
            return

        source_lock = runtime_cache.source_locks[pair.source_key]
        async with source_lock:
            source_entity, target_entity = await self._ensure_ads_entities(pair)
            msgs = await self._collect_ads_messages(pair, source_entity)
            await self._process_ads_messages(pair, source_entity, target_entity, msgs)

    async def _process_ads_messages(self, pair: AdsPairRecord, source_entity, target_entity, msgs) -> None:
        target_key = f"ads:{pair.target_chat_id or pair.target_input}"
        target_lock = runtime_cache.target_locks[target_key]
        grouped_seen: set[int] = set()

        async with target_lock:
            for msg in msgs:
                grouped_id = getattr(msg, "grouped_id", None)
                if grouped_id:
                    if grouped_id in grouped_seen:
                        continue
                    grouped_seen.add(grouped_id)
                    album = await collect_grouped_messages(source_entity, msg)
                    if not album:
                        continue
                    ids = [int(m.id) for m in album]
                    if any(mid in set(pair.recent_sent_ids) for mid in ids):
                        pair.last_processed_id = max(pair.last_processed_id, max(ids))
                        await self.ads_pairs.save(pair)
                        continue

                    await send_ads_pair_album(source_entity, target_entity, album)
                    pair.recent_sent_ids = (pair.recent_sent_ids + ids)[-200:]
                    pair.last_processed_id = max(pair.last_processed_id, max(ids))
                    pair.next_send_at = datetime.now(timezone.utc) + timedelta(seconds=pair.delay_seconds)
                    await self.ads_pairs.save(pair)
                    return

                msg_id = int(msg.id)
                if msg_id in set(pair.recent_sent_ids):
                    pair.last_processed_id = max(pair.last_processed_id, msg_id)
                    await self.ads_pairs.save(pair)
                    continue

                await send_ads_pair_single(source_entity, target_entity, msg)
                pair.recent_sent_ids = (pair.recent_sent_ids + [msg_id])[-200:]
                pair.last_processed_id = max(pair.last_processed_id, msg_id)
                pair.next_send_at = datetime.now(timezone.utc) + timedelta(seconds=pair.delay_seconds)
                await self.ads_pairs.save(pair)
                return
    
    async def _collect_messages(self, pair: PairRecord, source_entity):
        last_id = int(pair.last_processed_id or 0)
        if last_id == 0:
            latest = await safe_get_messages(source_entity, limit=pair.scan_count or None)
            return sorted([m for m in latest], key=lambda x: x.id)

        msgs = []
        async for msg in client.iter_messages(
            source_entity,
            min_id=last_id,
            reverse=True,
        ):
            msgs.append(msg)
        return msgs

    async def scan_pair(self, pair: PairRecord) -> None:
        source_lock = runtime_cache.source_locks[pair.source_key]
        self._active_checks[pair.source_key] += 1
        try:
            async with source_lock:
                source_entity, target_entity = await self._ensure_entities(pair)
                msgs = await self._collect_messages(pair, source_entity)
                await self._process_messages(pair, source_entity, target_entity, msgs)
        finally:
            self._active_checks[pair.source_key] = max(
                0,
                self._active_checks[pair.source_key] - 1,
            )

    async def scan_pair_manual(self, pair: PairRecord) -> None:
        """
        Manual Check path:
        - bypasses poll interval entirely
        - does not wait for source_lock, so it can fetch immediately even if
          background scan is currently busy collecting/sending for the same source
        - still uses target_lock through _process_messages to avoid overlapping sends
        """
        self._active_checks[pair.source_key] += 1
        try:
            source_entity, target_entity = await self._ensure_entities(pair)
            msgs = await self._collect_messages(pair, source_entity)
            await self._process_messages(pair, source_entity, target_entity, msgs)
        finally:
            self._active_checks[pair.source_key] = max(
                0,
                self._active_checks[pair.source_key] - 1,
            )

    async def _process_messages(self, pair: PairRecord, source_entity, target_entity, msgs) -> None:
        target_key = str(pair.target_chat_id or pair.target_input)
        target_lock = runtime_cache.target_locks[target_key]
        grouped_seen: set[int] = set()

        async with target_lock:
            for msg in msgs:
                grouped_id = getattr(msg, "grouped_id", None)
                if grouped_id:
                    if grouped_id in grouped_seen:
                        continue
                    grouped_seen.add(grouped_id)
                    album = await collect_grouped_messages(source_entity, msg)
                    await self.process_album(pair, source_entity, target_entity, album)
                else:
                    await self.process_single(pair, source_entity, target_entity, msg)

    def is_busy(self, pair: PairRecord) -> bool:
        return self._active_checks.get(pair.source_key, 0) > 0

    async def process_single(self, pair: PairRecord, source_entity, target_entity, msg) -> None:
        msg_id = int(msg.id)

        if is_duplicate(pair, [msg_id]):
            pair.last_processed_id = max(pair.last_processed_id, msg_id)
            await self.pairs.save(pair)
            return

        main_allowed = should_process_single(pair, msg)

        if pair.post_rule and is_video_message(msg) and main_allowed:
            try:
                await self._send_preview_for_message(pair, source_entity, target_entity, msg)
            except Exception:
                logger.exception(
                    "Preview send failed for pair user_id=%s pair_no=%s msg_id=%s",
                    pair.user_id,
                    pair.pair_no,
                    msg_id,
                )

        if main_allowed:
            await send_single(pair, source_entity, target_entity, msg)
            await self.notifier.clear_for_pair(pair)
            pair.recent_sent_ids = (pair.recent_sent_ids + [msg_id])[-200:]

        pair.last_processed_id = max(pair.last_processed_id, msg_id)
        await self.pairs.save(pair)

    async def process_album(self, pair: PairRecord, source_entity, target_entity, album) -> None:
        if not album:
            return

        ids = [int(m.id) for m in album]

        if is_duplicate(pair, ids):
            pair.last_processed_id = max(pair.last_processed_id, max(ids))
            await self.pairs.save(pair)
            return

        main_allowed = should_process_album(pair, album)

        if pair.post_rule and any(is_video_message(m) for m in album) and main_allowed:
            try:
                prev = await self._find_previous_message_before(source_entity, min(ids))
                if prev:
                    if getattr(prev, "grouped_id", None):
                        preview_album = await collect_grouped_messages(source_entity, prev)
                        preview_ids = [int(m.id) for m in preview_album]
                        if (
                            preview_album
                            and not is_duplicate(pair, preview_ids)
                            and should_process_album(
                                pair,
                                preview_album,
                                bypass_post_rule=True,
                            )
                        ):
                            await send_album(
                                pair,
                                source_entity,
                                target_entity,
                                preview_album,
                                bypass_post_rule=True,
                            )
                            pair.recent_sent_ids = (pair.recent_sent_ids + preview_ids)[-200:]
                    else:
                        prev_id = int(prev.id)
                        if (
                            not is_duplicate(pair, [prev_id])
                            and should_process_single(
                                pair,
                                prev,
                                bypass_post_rule=True,
                            )
                        ):
                            await send_single(pair, source_entity, target_entity, prev)
                            pair.recent_sent_ids = (pair.recent_sent_ids + [prev_id])[-200:]
            except Exception:
                logger.exception(
                    "Album preview send failed for pair user_id=%s pair_no=%s album_ids=%s",
                    pair.user_id,
                    pair.pair_no,
                    ids,
                )

        if main_allowed:
            await send_album(pair, source_entity, target_entity, album)
            await self.notifier.clear_for_pair(pair)
            pair.recent_sent_ids = (pair.recent_sent_ids + ids)[-200:]

        pair.last_processed_id = max(pair.last_processed_id, max(ids))
        await self.pairs.save(pair)

    async def _notify_target_admin_required(self, pair: PairRecord) -> None:
        if self._bot is None:
            return
        try:
            await self.notifier.notify_target_admin_required(self._bot, pair)
        except Exception:
            logger.exception(
                "Failed to send target-admin notification user_id=%s pair_no=%s target=%s",
                pair.user_id,
                pair.pair_no,
                pair.target_input,
            )

    async def _find_previous_message_before(self, source_entity, current_id: int):
        if current_id <= 1:
            return None
        async for prev in client.iter_messages(
            source_entity,
            offset_id=current_id,
            reverse=False,
            limit=10,
        ):
            if int(prev.id) < current_id:
                return prev
        return None

    async def _send_preview_for_message(self, pair: PairRecord, source_entity, target_entity, msg) -> None:
        prev = await self._find_previous_message_before(source_entity, int(msg.id))
        if not prev:
            return

        if getattr(prev, "grouped_id", None):
            preview_album = await collect_grouped_messages(source_entity, prev)
            preview_ids = [int(m.id) for m in preview_album]
            if (
                preview_album
                and not is_duplicate(pair, preview_ids)
                and should_process_album(
                    pair,
                    preview_album,
                    bypass_post_rule=True,
                )
            ):
                await send_album(
                    pair,
                    source_entity,
                    target_entity,
                    preview_album,
                    bypass_post_rule=True,
                )
                pair.recent_sent_ids = (pair.recent_sent_ids + preview_ids)[-200:]
        else:
            prev_id = int(prev.id)
            if (
                not is_duplicate(pair, [prev_id])
                and should_process_single(
                    pair,
                    prev,
                    bypass_post_rule=True,
                )
            ):
                await send_single(pair, source_entity, target_entity, prev)
                pair.recent_sent_ids = (pair.recent_sent_ids + [prev_id])[-200:]
                                
