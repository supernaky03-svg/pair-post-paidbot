
from __future__ import annotations

from typing import Iterable, List

from telethon.tl.types import DocumentAttributeVideo

from ..models import PairRecord


def normalize_chat_id(value: int | None) -> int | None:
    if value is None:
        return None
    return int(value)


def is_forwarded(msg) -> bool:
    return bool(getattr(msg, "fwd_from", None))


def is_video_message(msg) -> bool:
    if not msg:
        return False
    if getattr(msg, "video", None) or getattr(msg, "video_note", None):
        return True
    document = getattr(msg, "document", None)
    if document:
        mime = getattr(document, "mime_type", "") or ""
        if mime.startswith("video/"):
            return True
        for attr in getattr(document, "attributes", []):
            if isinstance(attr, DocumentAttributeVideo):
                return True
    return False


def message_text_for_filter(msg) -> str:
    raw = getattr(msg, "raw_text", None) or getattr(msg, "message", None) or ""
    return (raw or "").strip().lower()


def contains_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    haystack = (text or "").lower()
    return any(keyword in haystack for keyword in keywords if keyword)


def pair_keyword_allows_text(pair: PairRecord, text: str) -> bool:
    lowered = (text or "").lower()
    if pair.ban_keywords and contains_any_keyword(lowered, pair.ban_keywords):
        return False
    if pair.post_keywords:
        return contains_any_keyword(lowered, pair.post_keywords)
    return True


def pair_keyword_allows_message(pair: PairRecord, msg) -> bool:
    return pair_keyword_allows_text(pair, message_text_for_filter(msg))


def pair_keyword_allows_album(pair: PairRecord, album_messages: List[object]) -> bool:
    text = "\n".join(message_text_for_filter(m) for m in album_messages if m)
    return pair_keyword_allows_text(pair, text)


def pair_matches_filters(pair: PairRecord, msg) -> bool:
    if pair.forward_rule and is_forwarded(msg):
        return False
    if not pair_keyword_allows_message(pair, msg):
        return False
    if not pair.post_rule:
        return True
    return is_video_message(msg)


def pair_album_matches_filters(pair: PairRecord, album_messages: List[object]) -> bool:
    if pair.forward_rule and any(is_forwarded(m) for m in album_messages):
        return False
    if not pair_keyword_allows_album(pair, album_messages):
        return False
    if not pair.post_rule:
        return True
    return any(is_video_message(m) for m in album_messages)


def should_skip_forwarded(pair: PairRecord, msg) -> bool:
    return pair.forward_rule and is_forwarded(msg)


def should_skip_album_forwarded(pair: PairRecord, album_messages: List[object]) -> bool:
    return pair.forward_rule and any(is_forwarded(m) for m in album_messages)
