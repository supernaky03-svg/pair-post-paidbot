from __future__ import annotations

import asyncio
import random
import re
from collections import defaultdict
from typing import Any, Iterable

from telethon.errors.rpcerrorlist import FileReferenceExpiredError,MediaCaptionTooLongError

from app.core.config import settings
from app.domain.models import PairRecord
from app.telegram.safe_ops import (
    safe_get_messages,
    safe_send_album,
    safe_send_file,
    safe_send_message,
)

# Remove common ad/share links from outgoing text while keeping the rest intact.
LINK_RE = re.compile(r"(?i)\b(?:https?://|www\.|t\.me/|telegram\.me/)\S+")
USERNAME_RE = re.compile(r"(?i)(?<!\w)@[A-Za-z0-9_]{4,}(?!\w)")
MAX_MEDIA_CAPTION_LENGTH = 1024
MAX_TEXT_MESSAGE_LENGTH = 4096


def message_text(msg: Any) -> str:
    return ((getattr(msg, "message", None) or "") or (getattr(msg, "raw_text", None) or "")).strip()


def strip_links_preserve_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = LINK_RE.sub("", raw_line)
        line = USERNAME_RE.sub("", line)
        line = re.sub(r"[ \t]{2,}", " ", line).strip()
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def maybe_clean_text(pair: PairRecord, text: str) -> str:
    if pair.remove_url_rule:
        return strip_links_preserve_text(text)
    return (text or "").strip()


def is_forwarded(msg: Any) -> bool:
    return bool(getattr(msg, "fwd_from", None))


def is_video_message(msg: Any) -> bool:
    if getattr(msg, "video", False):
        return True

    media = getattr(msg, "media", None)
    if media is None:
        return False

    document = getattr(media, "document", None)
    if not document:
        return False

    for attr in getattr(document, "attributes", []):
        if attr.__class__.__name__.lower() == "documentattributevideo":
            return True

    mime_type = getattr(document, "mime_type", "") or ""
    return mime_type.startswith("video/")


def collect_album_text(album: Iterable[Any]) -> str:
    parts = [message_text(m) for m in album if message_text(m)]
    return "\n".join(parts).strip()


def keyword_match(text: str, keywords: list[str]) -> bool:
    text = (text or "").lower()
    return any(k.lower() in text for k in keywords)


def pair_keyword_allows_text(pair: PairRecord, text: str) -> bool:
    if pair.keyword_mode == "off" or not pair.keyword_values:
        return True

    has_match = keyword_match(text, pair.keyword_values)

    if pair.keyword_mode == "ban":
        return not has_match
    if pair.keyword_mode == "post":
        return has_match
    return True


def pair_keyword_allows_message(pair: PairRecord, msg: Any) -> bool:
    return pair_keyword_allows_text(pair, message_text(msg))


def pair_keyword_allows_album(pair: PairRecord, album: list[Any]) -> bool:
    return pair_keyword_allows_text(pair, collect_album_text(album))


def should_skip_forwarded(pair: PairRecord, msg: Any) -> bool:
    return pair.forward_rule and is_forwarded(msg)


def should_skip_album_forwarded(pair: PairRecord, album: list[Any]) -> bool:
    return pair.forward_rule and any(is_forwarded(m) for m in album)


def append_ads(text: str, ads: list[str]) -> str:
    ads = [a.strip() for a in ads if a and a.strip()]
    if not ads:
        return text.strip()

    joined = "\n".join(ads)
    return f"{text.strip()}\n\n{joined}".strip() if text.strip() else joined


def build_single_text(pair: PairRecord, msg: Any) -> str:
    cleaned = maybe_clean_text(pair, message_text(msg))
    return append_ads(cleaned, pair.ads)


def build_album_captions(pair: PairRecord, album: list[Any]) -> list[str]:
    ads_text = "\n".join(a.strip() for a in pair.ads if a.strip())
    captions: list[str] = []

    for index, msg in enumerate(album):
        text = maybe_clean_text(pair, message_text(msg))
        if index == 0 and ads_text:
            captions.append(f"{text}\n\n{ads_text}".strip())
        else:
            captions.append(text)

    return captions


def is_duplicate(pair: PairRecord, msg_ids: list[int]) -> bool:
    sent = set(pair.recent_sent_ids)
    return any(mid in sent for mid in msg_ids)


def should_process_single(pair: PairRecord, msg: Any, *, bypass_post_rule: bool = False) -> bool:
    if should_skip_forwarded(pair, msg):
        return False
    if not pair_keyword_allows_message(pair, msg):
        return False
    if pair.post_rule and not bypass_post_rule and not is_video_message(msg):
        return False
    return True


def should_process_album(pair: PairRecord, album: list[Any], *, bypass_post_rule: bool = False) -> bool:
    if should_skip_album_forwarded(pair, album):
        return False
    if not pair_keyword_allows_album(pair, album):
        return False
    if pair.post_rule and not bypass_post_rule and not any(is_video_message(m) for m in album):
        return False
    return True


class RuntimeCache:
    def __init__(self) -> None:
        self.source_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.target_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.entities: dict[tuple[int, int], dict[str, Any]] = {}

    def get_pair_entities(self, user_id: int, pair_no: int) -> dict[str, Any]:
        return self.entities.setdefault((user_id, pair_no), {"source": None, "target": None})

    def clear_pair(self, user_id: int, pair_no: int) -> None:
        self.entities.pop((user_id, pair_no), None)

    def clear_all(self) -> None:
        self.entities.clear()


runtime_cache = RuntimeCache()


async def human_delay() -> None:
    low = min(settings.delay_min_seconds, settings.delay_max_seconds)
    high = max(settings.delay_min_seconds, settings.delay_max_seconds)
    if high <= 0:
        return
    await asyncio.sleep(random.randint(low, high) if high > low else high)


async def _refetch_message(source_entity, msg_id: int):
    fresh = await safe_get_messages(source_entity, ids=msg_id)
    if isinstance(fresh, list):
        return fresh[0] if fresh else None
    return fresh


async def _refetch_album(source_entity, album: list[Any]) -> list[Any]:
    ids = [int(m.id) for m in album]
    fresh = await safe_get_messages(source_entity, ids=ids)
    if not fresh:
        return []
    if not isinstance(fresh, list):
        fresh = [fresh]
    by_id = {int(m.id): m for m in fresh if m}
    return [by_id[i] for i in ids if i in by_id]


def _chunk_text(text: str, limit: int = MAX_TEXT_MESSAGE_LENGTH) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit

        chunk = text[:cut].strip()
        if chunk:
            chunks.append(chunk)
        text = text[cut:].strip()

    if text:
        chunks.append(text)

    return chunks


async def _send_long_text(target_entity, text: str | None) -> None:
    for chunk in _chunk_text(text or ""):
        await safe_send_message(target_entity, chunk)


def _split_media_caption(text: str | None) -> tuple[str | None, str | None]:
    text = (text or "").strip()
    if not text:
        return None, None

    if len(text) <= MAX_MEDIA_CAPTION_LENGTH:
        return text, None

    cut = text.rfind("\n", 0, MAX_MEDIA_CAPTION_LENGTH)
    if cut <= 0:
        cut = text.rfind(" ", 0, MAX_MEDIA_CAPTION_LENGTH)
    if cut <= 0:
        cut = MAX_MEDIA_CAPTION_LENGTH

    caption = text[:cut].strip()
    rest = text[cut:].strip()

    return caption or None, rest or None


async def _send_file_with_caption_fallback(target_entity, media, text: str | None) -> None:
    caption, rest = _split_media_caption(text)

    try:
        await safe_send_file(target_entity, media, caption=caption)
    except MediaCaptionTooLongError:
        await safe_send_file(target_entity, media, caption=None)
        rest = text

    if rest:
        await _send_long_text(target_entity, rest)


def _prepare_album_captions(captions: list[str]) -> tuple[list[str], str | None]:
    limited: list[str] = []
    rest_parts: list[str] = []

    for caption in captions:
        limited_caption, rest = _split_media_caption(caption)
        limited.append(limited_caption or "")
        if rest:
            rest_parts.append(rest)

    rest_text = "\n\n".join(part for part in rest_parts if part.strip()).strip()
    return limited, rest_text or None


async def _send_album_with_caption_fallback(target_entity, files, captions: list[str]) -> None:
    limited_captions, rest_text = _prepare_album_captions(captions)

    try:
        await safe_send_album(target_entity, files, limited_captions)
    except MediaCaptionTooLongError:
        await safe_send_album(target_entity, files, [""] * len(files))
        rest_text = "\n\n".join(c for c in captions if c and c.strip()).strip()

    if rest_text:
        await _send_long_text(target_entity, rest_text)


async def send_single(pair: PairRecord, source_entity, target_entity, msg: Any) -> None:
    await human_delay()

    if getattr(msg, "media", None):
        caption = build_single_text(pair, msg)

        try:
            await _send_file_with_caption_fallback(target_entity, msg.media, caption)
        except FileReferenceExpiredError:
            fresh = await _refetch_message(source_entity, int(msg.id))
            if not fresh or not getattr(fresh, "media", None):
                raise

            await _send_file_with_caption_fallback(
                target_entity,
                fresh.media,
                build_single_text(pair, fresh),
            )

    else:
        text = build_single_text(pair, msg)
        if text:
            await _send_long_text(target_entity, text)


async def send_album(
    pair: PairRecord,
    source_entity,
    target_entity,
    album: list[Any],
    *,
    bypass_post_rule: bool = False,
) -> None:
    await human_delay()

    files = [m.media for m in album if getattr(m, "media", None)]
    captions = build_album_captions(pair, album)

    if files:
        try:
            await _send_album_with_caption_fallback(target_entity, files, captions)
        except FileReferenceExpiredError:
            fresh_album = await _refetch_album(source_entity, album)
            fresh_files = [m.media for m in fresh_album if getattr(m, "media", None)]
            if not fresh_files:
                raise

            await _send_album_with_caption_fallback(
                target_entity,
                fresh_files,
                build_album_captions(pair, fresh_album),
            )

    else:
        text = append_ads(maybe_clean_text(pair, collect_album_text(album)), pair.ads)
        if text:
            await _send_long_text(target_entity, text)


async def collect_grouped_messages(source_entity, msg_or_id: Any) -> list[Any]:
    source_msg_id = msg_or_id if isinstance(msg_or_id, int) else int(msg_or_id.id)
    around = await safe_get_messages(source_entity, limit=40)
    source_msg = next((m for m in around if int(m.id) == source_msg_id), None)
    if not source_msg:
        return []

    grouped_id = getattr(source_msg, "grouped_id", None)
    if not grouped_id:
        return [source_msg]

    items = [m for m in around if getattr(m, "grouped_id", None) == grouped_id]
    return sorted(items, key=lambda x: x.id)
        
