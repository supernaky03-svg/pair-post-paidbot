
from __future__ import annotations

import asyncio
import random
from typing import Any, List

from ..core.logging import logger
from ..core.runtime import cache_pair, get_pair_runtime, get_runtime
from ..db.repositories import Repository
from ..models import PairRecord
from ..utils.filters import (
    is_video_message,
    pair_album_matches_filters,
    pair_matches_filters,
    should_skip_album_forwarded,
    should_skip_forwarded,
)
from ..utils.telethon import (
    safe_get_message,
    safe_get_messages,
    safe_send_album,
    safe_send_file,
    safe_send_message,
)
from ..utils.text import build_album_captions, build_single_caption, build_single_text
from .entity import resolve_pair_entities


def is_duplicate(pair: PairRecord, msg_id: int) -> bool:
    return int(msg_id) in set(int(item) for item in pair.recent_sent_ids)

async def persist_pair(pair: PairRecord) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    saved = await repo.upsert_pair(pair)
    cache_pair(saved)
    return saved

async def mark_sent_ids(pair: PairRecord, msg_ids: List[int]) -> PairRecord:
    runtime = get_runtime()
    pair.recent_sent_ids.extend(int(item) for item in msg_ids)
    pair.recent_sent_ids = pair.recent_sent_ids[-runtime.settings.recent_ids_limit :]
    return await persist_pair(pair)

async def update_last_processed(pair: PairRecord, msg_id: int) -> PairRecord:
    if int(msg_id) > int(pair.last_processed_id):
        pair.last_processed_id = int(msg_id)
        return await persist_pair(pair)
    return pair

async def apply_human_delay() -> None:
    settings = get_runtime().settings
    low = min(settings.delay_min_seconds, settings.delay_max_seconds)
    high = max(settings.delay_min_seconds, settings.delay_max_seconds)
    if high <= 0:
        return
    delay = random.randint(low, high) if high > low else high
    if delay > 0:
        await asyncio.sleep(delay)

async def mark_action_done(pair: PairRecord, msg_ids: List[int]) -> PairRecord:
    await mark_sent_ids(pair, msg_ids)
    return await update_last_processed(pair, max(msg_ids))

async def repost_single_message(
    pair: PairRecord,
    msg,
    bypass_post_rule: bool = False,
) -> bool:
    runtime = get_pair_runtime(pair.owner_user_id, pair.pair_id)
    target_entity = runtime.target_entity
    if not target_entity:
        return False
    msg_id = int(msg.id)

    if is_duplicate(pair, msg_id):
        logger.info("Skipping duplicate message %s for pair %s", msg_id, pair.pair_id)
        await update_last_processed(pair, msg_id)
        return False

    if not bypass_post_rule:
        if not pair_matches_filters(pair, msg):
            logger.info("Skipping message %s for pair %s due to filters", msg_id, pair.pair_id)
            await update_last_processed(pair, msg_id)
            return False
    else:
        if should_skip_forwarded(pair, msg):
            logger.info(
                "Skipping preview message %s for pair %s because it is forwarded",
                msg_id,
                pair.pair_id,
            )
            await update_last_processed(pair, msg_id)
            return False

    await apply_human_delay()
    if msg.media:
        caption = build_single_caption(pair, msg)
        await safe_send_file(target_entity, msg.media, caption=caption)
    else:
        text = build_single_text(pair, msg)
        if not text:
            logger.info("Skipping empty text message %s for pair %s", msg_id, pair.pair_id)
            await update_last_processed(pair, msg_id)
            return False
        await safe_send_message(target_entity, text)

    logger.info("Reposted single message %s for pair %s", msg_id, pair.pair_id)
    await mark_action_done(pair, [msg_id])
    return True

async def repost_album(
    pair: PairRecord,
    album_messages: List[Any],
    bypass_post_rule: bool = False,
) -> bool:
    runtime = get_pair_runtime(pair.owner_user_id, pair.pair_id)
    target_entity = runtime.target_entity
    if not target_entity or not album_messages:
        return False
    grouped_id = getattr(album_messages[0], "grouped_id", None)
    msg_ids = [int(m.id) for m in album_messages]

    if grouped_id in runtime.last_sent_grouped_ids:
        logger.info("Skipping duplicate runtime album %s for pair %s", grouped_id, pair.pair_id)
        await update_last_processed(pair, max(msg_ids))
        return False
    if any(is_duplicate(pair, mid) for mid in msg_ids):
        logger.info(
            "Skipping album %s for pair %s because one or more items already sent",
            grouped_id,
            pair.pair_id,
        )
        await update_last_processed(pair, max(msg_ids))
        return False

    if not bypass_post_rule:
        if not pair_album_matches_filters(pair, album_messages):
            logger.info("Skipping album %s for pair %s due to filters", grouped_id, pair.pair_id)
            await update_last_processed(pair, max(msg_ids))
            return False
    else:
        if should_skip_album_forwarded(pair, album_messages):
            logger.info(
                "Skipping preview album %s for pair %s because it is forwarded",
                grouped_id,
                pair.pair_id,
            )
            await update_last_processed(pair, max(msg_ids))
            return False

    if pair.post_rule and not bypass_post_rule:
        files = []
        captions = []
        for msg, caption in zip(album_messages, build_album_captions(pair, album_messages)):
            if is_video_message(msg) and msg.media:
                files.append(msg.media)
                captions.append(caption or "")
        if not files:
            logger.info(
                "Skipping album %s for pair %s because post_rule=ON and no video items found",
                grouped_id,
                pair.pair_id,
            )
            await update_last_processed(pair, max(msg_ids))
            return False
    else:
        files = [m.media for m in album_messages if m.media]
        captions = build_album_captions(pair, album_messages)

    if not files:
        text_parts = [caption for caption in captions if caption]
        text = "\n\n".join(text_parts).strip()
        if not text:
            logger.info("Skipping media-less album %s for pair %s", grouped_id, pair.pair_id)
            await update_last_processed(pair, max(msg_ids))
            return False
        await apply_human_delay()
        await safe_send_message(target_entity, text)
        if grouped_id is not None:
            runtime.last_sent_grouped_ids.add(grouped_id)
        await mark_action_done(pair, msg_ids)
        return True

    await apply_human_delay()
    await safe_send_album(target_entity, files, captions)
    if grouped_id is not None:
        runtime.last_sent_grouped_ids.add(grouped_id)
    logger.info("Reposted album %s for pair %s", grouped_id, pair.pair_id)
    await mark_action_done(pair, msg_ids)
    return True

async def collect_grouped_album_messages(source_entity, msg) -> List[Any]:
    grouped_id = getattr(msg, "grouped_id", None)
    if not grouped_id:
        return [msg]
    batch = await safe_get_messages(source_entity, limit=30)
    items = [item for item in batch if getattr(item, "grouped_id", None) == grouped_id]
    items = sorted(items, key=lambda item: item.id)
    if msg.id not in {item.id for item in items}:
        items.append(msg)
    return sorted(items, key=lambda item: item.id)

async def repost_preview_for_video(pair: PairRecord, msg) -> None:
    if not pair.post_rule:
        return
    if not is_video_message(msg):
        return
    runtime = get_pair_runtime(pair.owner_user_id, pair.pair_id)
    source_entity = runtime.source_entity
    if not source_entity:
        return
    previous_id = int(msg.id) - 1
    if previous_id <= 0:
        return
    previous_msg = await safe_get_message(source_entity, previous_id)
    if not previous_msg:
        return
    if getattr(previous_msg, "grouped_id", None):
        preview_album = await collect_grouped_album_messages(source_entity, previous_msg)
        if should_skip_album_forwarded(pair, preview_album):
            return
        if any(is_duplicate(pair, int(item.id)) for item in preview_album):
            return
        await repost_album(pair, preview_album, bypass_post_rule=True)
        return
    if should_skip_forwarded(pair, previous_msg):
        return
    if is_duplicate(pair, int(previous_msg.id)):
        return
    await repost_single_message(pair, previous_msg, bypass_post_rule=True)

async def process_message_object(pair: PairRecord, msg) -> None:
    runtime = get_pair_runtime(pair.owner_user_id, pair.pair_id)
    async with runtime.lock:
        resolved = runtime.source_entity is not None and runtime.target_entity is not None
        if not resolved:
            resolved = await resolve_pair_entities(pair)
            if resolved:
                await persist_pair(pair)
        if not resolved:
            return

        if should_skip_forwarded(pair, msg):
            await update_last_processed(pair, int(msg.id))
            return

        if pair.post_rule and is_video_message(msg):
            await repost_preview_for_video(pair, msg)
        await repost_single_message(pair, msg)

async def process_album_object(pair: PairRecord, album_messages: List[Any]) -> None:
    if not album_messages:
        return
    runtime = get_pair_runtime(pair.owner_user_id, pair.pair_id)
    album_messages = sorted(album_messages, key=lambda item: item.id)

    async with runtime.lock:
        resolved = runtime.source_entity is not None and runtime.target_entity is not None
        if not resolved:
            resolved = await resolve_pair_entities(pair)
            if resolved:
                await persist_pair(pair)
        if not resolved:
            return

        if should_skip_album_forwarded(pair, album_messages):
            await update_last_processed(pair, max(int(item.id) for item in album_messages))
            return

        if pair.post_rule:
            first_video = next((item for item in album_messages if is_video_message(item)), None)
            if first_video:
                prev_id = int(min(item.id for item in album_messages)) - 1
                if prev_id > 0:
                    previous_msg = await safe_get_message(runtime.source_entity, prev_id)
                    if previous_msg:
                        if getattr(previous_msg, "grouped_id", None):
                            preview_album = await collect_grouped_album_messages(runtime.source_entity, previous_msg)
                            if not should_skip_album_forwarded(pair, preview_album):
                                if not any(is_duplicate(pair, int(item.id)) for item in preview_album):
                                    await repost_album(pair, preview_album, bypass_post_rule=True)
                        else:
                            if not should_skip_forwarded(pair, previous_msg):
                                if not is_duplicate(pair, int(previous_msg.id)):
                                    await repost_single_message(pair, previous_msg, bypass_post_rule=True)
        await repost_album(pair, album_messages)
