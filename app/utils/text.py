
from __future__ import annotations

import re
from typing import List, Optional

from ..models import PairRecord
from .filters import is_video_message

URL_REGEX = re.compile(r'(?i)\b(?:https?://|www\.|t\.me/)\S+')
USERNAME_REGEX = re.compile(r'(?<![\w])@[A-Za-z0-9_]{5,}')


def clean_urls(text: str) -> str:
    if not text:
        return ""
    cleaned = URL_REGEX.sub("", text)
    cleaned = USERNAME_REGEX.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"<\s*>", "", cleaned)
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def clean_and_add_ads(text: str, ads_links: list[str] | None = None) -> str:
    base = clean_urls(text or "")
    links = [item.strip() for item in (ads_links or []) if item and item.strip()]
    if not links:
        return base
    suffix = "\n".join(links)
    return f"{base}\n\n{suffix}".strip() if base else suffix


def get_clean_text_from_message(msg) -> str:
    raw = getattr(msg, "raw_text", None) or getattr(msg, "message", None) or ""
    return clean_urls(raw)


def build_single_text(pair: PairRecord, msg) -> Optional[str]:
    final_text = clean_and_add_ads(get_clean_text_from_message(msg), pair.ads_links)
    return final_text or None


def build_single_caption(pair: PairRecord, msg) -> Optional[str]:
    final_caption = clean_and_add_ads(get_clean_text_from_message(msg), pair.ads_links)
    return final_caption or None


def build_album_captions(pair: PairRecord, album_messages: List[object]) -> List[str]:
    captions: list[str] = []
    first_video_index = None
    for idx, item in enumerate(album_messages):
        if is_video_message(item):
            first_video_index = idx
            break
    if first_video_index is None and album_messages:
        first_video_index = 0

    for idx, msg in enumerate(album_messages):
        base_caption = get_clean_text_from_message(msg)
        if pair.ads_links and first_video_index is not None and idx == first_video_index:
            captions.append(clean_and_add_ads(base_caption, pair.ads_links))
        else:
            captions.append(base_caption)
    return captions
