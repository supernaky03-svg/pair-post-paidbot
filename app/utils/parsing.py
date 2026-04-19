
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from dateutil.relativedelta import relativedelta

from ..models import SCAN_COUNT_ALL

INVITE_LINK_RE = re.compile(r"(?i)(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/|\+)([A-Za-z0-9_-]+)")
TG_JOIN_INVITE_RE = re.compile(r"(?i)tg://join\?invite=([A-Za-z0-9_-]+)")


class ParseError(ValueError):
    pass


def normalize_keyword_list(value: str | Iterable[str] | None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split(",") if "," in value else value.split()
    else:
        items = list(value)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        keyword = str(item or "").strip().lower()
        if not keyword or keyword in seen:
            continue
        normalized.append(keyword)
        seen.add(keyword)
    return normalized


def parse_pair_number(value: str) -> int:
    text = (value or "").strip().lower()
    if text == "auto":
        return 0
    if not re.fullmatch(r"\d+", text):
        raise ParseError("Pair number must be a positive integer or auto.")
    number = int(text)
    if number <= 0:
        raise ParseError("Pair number must be greater than 0.")
    return number


def parse_scan_amount(value: str, default: int = 100) -> int:
    text = (value or "").strip().lower()
    if not text:
        return default
    if text == "all":
        return SCAN_COUNT_ALL
    if not re.fullmatch(r"\d+", text):
        raise ParseError("Scan amount must be a positive number or all.")
    number = int(text)
    if number <= 0:
        raise ParseError("Scan amount must be greater than 0.")
    return number


def format_scan_amount(value: int) -> str:
    return "all" if int(value) == SCAN_COUNT_ALL else str(value)


def parse_id_or_all(value: str) -> str:
    text = (value or "").strip().lower()
    if text == "all":
        return "all"
    if not re.fullmatch(r"\d+", text):
        raise ParseError("Type a pair number or all.")
    return text


def extract_invite_hash(value: str) -> Optional[str]:
    text = (value or "").strip()
    match = INVITE_LINK_RE.search(text)
    if match:
        return match.group(1)
    match = TG_JOIN_INVITE_RE.search(text)
    if match:
        return match.group(1)
    return None


def parse_duration_token(token: str) -> tuple[int, str]:
    text = (token or "").strip().lower()
    match = re.fullmatch(r"(\d+)([dwmy])", text)
    if not match:
        raise ParseError("Duration must look like 7d, 2w, 1m, or 1y.")
    value = int(match.group(1))
    unit = match.group(2)
    if value <= 0:
        raise ParseError("Duration value must be positive.")
    return value, unit


def apply_duration(start: datetime, value: int, unit: str) -> datetime:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if unit == "d":
        return start + timedelta(days=value)
    if unit == "w":
        return start + timedelta(weeks=value)
    if unit == "m":
        return start + relativedelta(months=value)
    if unit == "y":
        return start + relativedelta(years=value)
    raise ParseError("Unsupported duration unit.")


def format_expiry(dt: datetime | None) -> str:
    if not dt:
        return "-"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
