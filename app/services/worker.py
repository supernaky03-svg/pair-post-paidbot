
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, List

from telethon import events

from ..core.logging import logger
from ..core.runtime import (
    AppRuntime,
    cache_pair,
    get_pairs_for_source_chat,
    get_runtime,
    get_user,
    list_user_pairs,
)
from ..db.repositories import Repository
from ..models import PairRecord, SCAN_COUNT_ALL
from ..services.entity import resolve_pair_entities
from ..services.queueing import SourceQueueManager
from ..utils.filters import normalize_chat_id
from ..utils.telethon import run_with_floodwait, safe_get_messages
from .reposting import process_album_object, process_message_object


async def fetch_latest_message_id(source_entity) -> int:
    latest = await safe_get_messages(source_entity, limit=1)
    if latest and len(latest) > 0:
        return int(latest[0].id)
    return 0


async def _submit_pair_job(pair: PairRecord, description: str, factory):
    runtime = get_runtime()
    return await runtime.source_queue_manager.submit(pair.source_queue_key(), factory, description)


async def process_live_message_for_pair(pair: PairRecord, msg) -> None:
    await _submit_pair_job(
        pair,
        f"live-message:{pair.pair_id}:{getattr(msg, 'id', '?')}",
        lambda: process_message_object(pair, msg),
    )

async def process_live_album_for_pair(pair: PairRecord, messages: list[object]) -> None:
    await _submit_pair_job(
        pair,
        f"live-album:{pair.pair_id}:{getattr(messages[0], 'grouped_id', '?')}",
        lambda: process_album_object(pair, messages),
    )

async def scan_pair(pair: PairRecord) -> None:
    resolved = await resolve_pair_entities(pair)
    if not resolved:
        return

    runtime = get_runtime()
    repo = Repository(runtime.db)
    await repo.upsert_pair(pair)
    cache_pair(pair)

    source_runtime = runtime.pair_runtime[(pair.owner_user_id, pair.pair_id)]
    source_entity = source_runtime.source_entity
    last_processed_id = int(pair.last_processed_id)
    initial_scan_limit = None if pair.scan_amount == SCAN_COUNT_ALL else int(pair.scan_amount)

    logger.info(
        "Scan begin for user=%s pair=%s | last_processed_id=%s | initial_scan=%s",
        pair.owner_user_id,
        pair.pair_id,
        last_processed_id,
        "all" if initial_scan_limit is None else initial_scan_limit,
    )

    try:
        grouped_map: Dict[int, List[Any]] = defaultdict(list)
        if last_processed_id == 0:
            if initial_scan_limit is None:
                async for msg in runtime.telethon.iter_messages(source_entity, reverse=True):
                    grouped_id = getattr(msg, "grouped_id", None)
                    if grouped_id:
                        grouped_map[grouped_id].append(msg)
                    else:
                        await _submit_pair_job(
                            pair,
                            f"scan-message:{pair.pair_id}:{msg.id}",
                            lambda pair=pair, msg=msg: process_message_object(pair, msg),
                        )
            else:
                latest_msgs = await run_with_floodwait(
                    runtime.telethon.get_messages,
                    source_entity,
                    limit=initial_scan_limit,
                )
                latest_msgs = sorted(latest_msgs, key=lambda item: item.id)
                for msg in latest_msgs:
                    grouped_id = getattr(msg, "grouped_id", None)
                    if grouped_id:
                        grouped_map[grouped_id].append(msg)
                    else:
                        await _submit_pair_job(
                            pair,
                            f"scan-message:{pair.pair_id}:{msg.id}",
                            lambda pair=pair, msg=msg: process_message_object(pair, msg),
                        )
        else:
            current_latest_id = await fetch_latest_message_id(source_entity)
            if current_latest_id > last_processed_id:
                async for msg in runtime.telethon.iter_messages(
                    source_entity,
                    min_id=last_processed_id,
                    reverse=True,
                ):
                    grouped_id = getattr(msg, "grouped_id", None)
                    if grouped_id:
                        grouped_map[grouped_id].append(msg)
                    else:
                        await _submit_pair_job(
                            pair,
                            f"rescan-message:{pair.pair_id}:{msg.id}",
                            lambda pair=pair, msg=msg: process_message_object(pair, msg),
                        )

        for _, album_msgs in sorted(grouped_map.items(), key=lambda item: min(m.id for m in item[1])):
            await _submit_pair_job(
                pair,
                f"scan-album:{pair.pair_id}:{getattr(album_msgs[0], 'grouped_id', '?')}",
                lambda pair=pair, album_msgs=album_msgs: process_album_object(pair, album_msgs),
            )

        latest_msgs = await run_with_floodwait(
            runtime.telethon.get_messages,
            source_entity,
            limit=runtime.settings.latest_recheck_limit,
        )
        latest_msgs = sorted(latest_msgs, key=lambda item: item.id)
        grouped_map_2: Dict[int, List[Any]] = defaultdict(list)
        for msg in latest_msgs:
            grouped_id = getattr(msg, "grouped_id", None)
            if grouped_id:
                grouped_map_2[grouped_id].append(msg)
            else:
                await _submit_pair_job(
                    pair,
                    f"latest-message:{pair.pair_id}:{msg.id}",
                    lambda pair=pair, msg=msg: process_message_object(pair, msg),
                )
        for _, album_msgs in sorted(grouped_map_2.items(), key=lambda item: min(m.id for m in item[1])):
            await _submit_pair_job(
                pair,
                f"latest-album:{pair.pair_id}:{getattr(album_msgs[0], 'grouped_id', '?')}",
                lambda pair=pair, album_msgs=album_msgs: process_album_object(pair, album_msgs),
            )
    except Exception:
        logger.exception("Scan failed for user=%s pair=%s", pair.owner_user_id, pair.pair_id)


async def scan_user_pairs(user_id: int) -> None:
    user = get_user(user_id)
    if not user or user.is_banned or not user.has_access():
        return
    for pair in list_user_pairs(user_id):
        await scan_pair(pair)


async def start_periodic_scanner(runtime: AppRuntime) -> None:
    runtime.source_queue_manager = SourceQueueManager()
    runtime.poll_stop_event.clear()
    while not runtime.poll_stop_event.is_set():
        try:
            active_user_ids = [
                user.telegram_user_id
                for user in runtime.users.values()
                if not user.is_banned and user.has_access()
            ]
            for user_id in active_user_ids:
                await scan_user_pairs(user_id)
        except Exception:
            logger.exception("Periodic scanner failed")
        try:
            await asyncio.wait_for(
                runtime.poll_stop_event.wait(),
                timeout=runtime.settings.poll_interval_seconds,
            )
        except asyncio.TimeoutError:
            pass


async def stop_periodic_scanner(runtime: AppRuntime) -> None:
    runtime.poll_stop_event.set()


def register_telethon_handlers(runtime: AppRuntime) -> None:
    @runtime.telethon.on(events.NewMessage)
    async def _on_new_message(event):
        source_chat_id = normalize_chat_id(getattr(event, "chat_id", None))
        if source_chat_id is None:
            return
        for pair in get_pairs_for_source_chat(source_chat_id):
            await process_live_message_for_pair(pair, event.message)

    @runtime.telethon.on(events.Album)
    async def _on_album(event):
        source_chat_id = normalize_chat_id(getattr(event, "chat_id", None))
        if source_chat_id is None:
            return
        messages = list(event.messages or [])
        if not messages:
            return
        for pair in get_pairs_for_source_chat(source_chat_id):
            await process_live_album_for_pair(pair, messages)
