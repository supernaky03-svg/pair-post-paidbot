
from __future__ import annotations

import asyncio
from typing import Iterable

from aiogram.types import User as TgUser

from ..core.runtime import (
    cache_pair,
    cache_user,
    clear_user_pairs,
    get_pair,
    get_runtime,
    get_user,
    list_user_pairs,
    remove_pair,
)
from ..db.repositories import Repository
from ..localization import t
from ..models import PairRecord, UserRecord, utc_now
from ..services.access import apply_restore_choice
from ..services.db_channel import mirror_user_snapshot, validate_database_channel
from ..services.entity import EntityResolutionError, resolve_entity_reference
from ..services.worker import scan_pair, scan_user_pairs
from ..utils.parsing import ParseError, apply_duration, format_scan_amount, normalize_keyword_list


class ActionError(ValueError):
    pass


def next_pair_id(user_id: int) -> int:
    current = list_user_pairs(user_id)
    return (max((item.pair_id for item in current), default=0) + 1) if current else 1


async def ensure_user_profile(telegram_user: TgUser) -> UserRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    user = await repo.upsert_user(telegram_user.id, telegram_user.username)
    cache_user(user)
    return user


async def get_fresh_user(user_id: int) -> UserRecord | None:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    user = await repo.get_user(user_id)
    if user:
        cache_user(user)
    return user


async def redeem_otp_for_user(user: UserRecord, key: str):
    runtime = get_runtime()
    repo = Repository(runtime.db)
    otp = await repo.get_otp(key)
    if not otp or otp.is_used:
        raise ActionError(t(user, "invalid_otp"))
    had_previous_data = bool(user.database_channel_id or list_user_pairs(user.telegram_user_id))
    had_expired_before = bool(user.access_expires_at and user.access_expires_at <= utc_now())
    expiry = __import__("app.utils.parsing", fromlist=["apply_duration"]).apply_duration(
        utc_now(), otp.duration_value, otp.duration_unit
    )
    await repo.mark_otp_used(key, user.telegram_user_id)
    user = await repo.update_user_access(user.telegram_user_id, expiry, otp.key)
    cache_user(user)
    needs_restore = had_previous_data and had_expired_before
    return user, expiry, needs_restore

async def apply_restore_option(user: UserRecord, mode: str) -> UserRecord:
    updated = await apply_restore_choice(user, mode)
    if mode == "reset":
        clear_user_pairs(user.telegram_user_id)
    await mirror_user_snapshot(updated, list_user_pairs(updated.telegram_user_id))
    return updated

async def save_database_channel(user: UserRecord, channel_id: int) -> UserRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    channel_id, channel_link = await validate_database_channel(channel_id)
    updated = await repo.update_user_database_channel(user.telegram_user_id, channel_id, channel_link)
    cache_user(updated)
    await mirror_user_snapshot(updated, list_user_pairs(updated.telegram_user_id))
    return updated

async def change_language(user: UserRecord, language: str) -> UserRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    updated = await repo.update_user_language(user.telegram_user_id, language)
    cache_user(updated)
    await mirror_user_snapshot(updated, list_user_pairs(updated.telegram_user_id))
    return updated

async def add_pair(
    user: UserRecord,
    *,
    pair_id_input: int,
    source_id: str,
    scan_amount: int,
    target_id: str,
    ads_links: list[str],
    post_rule: bool,
    forward_rule: bool,
) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)

    pairs = list_user_pairs(user.telegram_user_id)
    if len(pairs) >= user.effective_pair_limit(runtime.default_pair_limit):
        raise ActionError(t(user, "pair_limit_error"))

    pair_id = pair_id_input or next_pair_id(user.telegram_user_id)
    if get_pair(user.telegram_user_id, pair_id):
        raise ActionError(f"Pair {pair_id} already exists.")

    try:
        source_entity = await resolve_entity_reference(source_id, allow_join_via_invite=True)
        target_entity = await resolve_entity_reference(target_id, allow_join_via_invite=True)
    except EntityResolutionError as exc:
        raise ActionError(str(exc)) from exc

    source_chat_id = int(getattr(source_entity, "id", 0) or 0)
    same_source_count = sum(1 for pair in pairs if int(pair.source_chat_id or 0) == source_chat_id)
    if same_source_count >= 3:
        raise ActionError(t(user, "source_dup_limit_error"))

    pair = PairRecord(
        owner_user_id=user.telegram_user_id,
        pair_id=pair_id,
        source_id=source_id.strip(),
        target_id=target_id.strip(),
        source_chat_id=source_chat_id,
        target_chat_id=int(getattr(target_entity, "id", 0) or 0),
        last_processed_id=0,
        recent_sent_ids=[],
        forward_rule=bool(forward_rule),
        post_rule=bool(post_rule),
        scan_amount=int(scan_amount),
        ads_links=[item.strip() for item in ads_links if item.strip()],
        ban_keywords=[],
        post_keywords=[],
    )
    pair = await repo.upsert_pair(pair)
    cache_pair(pair)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))
    asyncio.create_task(scan_pair(pair))
    return pair

async def delete_pair_action(user: UserRecord, pair_id: int) -> None:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    existing = get_pair(user.telegram_user_id, pair_id)
    if not existing:
        raise ActionError(f"Pair {pair_id} not found.")
    await repo.delete_pair(user.telegram_user_id, pair_id)
    remove_pair(user.telegram_user_id, pair_id)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))

async def edit_source_action(user: UserRecord, pair_id: int, new_source: str, scan_amount: int) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    pair = get_pair(user.telegram_user_id, pair_id)
    if not pair:
        raise ActionError(f"Pair {pair_id} not found.")
    try:
        source_entity = await resolve_entity_reference(new_source, allow_join_via_invite=True)
    except EntityResolutionError as exc:
        raise ActionError(str(exc)) from exc

    new_source_chat_id = int(getattr(source_entity, "id", 0) or 0)
    same_source_count = sum(
        1
        for item in list_user_pairs(user.telegram_user_id)
        if item.pair_id != pair_id and int(item.source_chat_id or 0) == new_source_chat_id
    )
    if same_source_count >= 3:
        raise ActionError(t(user, "source_dup_limit_error"))

    pair.source_id = new_source.strip()
    pair.source_chat_id = new_source_chat_id
    pair.scan_amount = int(scan_amount)
    pair.last_processed_id = 0
    pair.recent_sent_ids = []
    pair = await repo.upsert_pair(pair)
    cache_pair(pair)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))
    asyncio.create_task(scan_pair(pair))
    return pair

async def edit_target_action(user: UserRecord, pair_id: int, new_target: str) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    pair = get_pair(user.telegram_user_id, pair_id)
    if not pair:
        raise ActionError(f"Pair {pair_id} not found.")
    try:
        target_entity = await resolve_entity_reference(new_target, allow_join_via_invite=True)
    except EntityResolutionError as exc:
        raise ActionError(str(exc)) from exc

    pair.target_id = new_target.strip()
    pair.target_chat_id = int(getattr(target_entity, "id", 0) or 0)
    pair = await repo.upsert_pair(pair)
    cache_pair(pair)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))
    return pair

async def update_keywords_action(
    user: UserRecord,
    pair_id: int,
    *,
    mode: str,
    add_values: str | None = None,
    remove_values: str | None = None,
    clear_all: bool = False,
) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    pair = get_pair(user.telegram_user_id, pair_id)
    if not pair:
        raise ActionError(f"Pair {pair_id} not found.")
    attr = "ban_keywords" if mode == "ban" else "post_keywords"
    current = list(getattr(pair, attr))
    if clear_all:
        setattr(pair, attr, [])
    elif add_values is not None:
        merged = current + normalize_keyword_list(add_values)
        setattr(pair, attr, normalize_keyword_list(merged))
    elif remove_values is not None:
        values = set(normalize_keyword_list(remove_values))
        setattr(pair, attr, [item for item in current if item not in values])
    pair = await repo.upsert_pair(pair)
    cache_pair(pair)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))
    return pair

async def set_ads_action(user: UserRecord, pair_id: int, ads_links: list[str]) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    pair = get_pair(user.telegram_user_id, pair_id)
    if not pair:
        raise ActionError(f"Pair {pair_id} not found.")
    pair.ads_links = [item.strip() for item in ads_links if item.strip()]
    pair = await repo.upsert_pair(pair)
    cache_pair(pair)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))
    return pair

async def toggle_rule_action(user: UserRecord, pair_id: int, rule_name: str, value: bool) -> PairRecord:
    runtime = get_runtime()
    repo = Repository(runtime.db)
    pair = get_pair(user.telegram_user_id, pair_id)
    if not pair:
        raise ActionError(f"Pair {pair_id} not found.")
    if rule_name == "forward":
        pair.forward_rule = value
    elif rule_name == "post":
        pair.post_rule = value
    else:
        raise ActionError("Unknown rule.")
    pair = await repo.upsert_pair(pair)
    cache_pair(pair)
    await mirror_user_snapshot(user, list_user_pairs(user.telegram_user_id))
    return pair

async def run_check_action(user: UserRecord, pair_choice: str) -> int:
    if pair_choice == "all":
        asyncio.create_task(scan_user_pairs(user.telegram_user_id))
        return len(list_user_pairs(user.telegram_user_id))
    pair = get_pair(user.telegram_user_id, int(pair_choice))
    if not pair:
        raise ActionError(f"Pair {pair_choice} not found.")
    asyncio.create_task(scan_pair(pair))
    return 1

def build_status_text(user: UserRecord) -> str:
    runtime = get_runtime()
    pairs = list_user_pairs(user.telegram_user_id)
    queue_pending = sum(
        runtime.source_queue_manager.pending_count(pair.source_queue_key())
        for pair in pairs
    ) if runtime.source_queue_manager else 0
    lines = [
        t(user, "status_title"),
        "",
        f"Database: {user.database_channel_link or '-'}",
        f"Access: {'active' if user.has_access() else 'expired'}",
        f"Expiry: {user.access_expires_at.strftime('%Y-%m-%d %H:%M UTC') if user.access_expires_at else '-'}",
        f"Pairs: {len(pairs)} / {user.effective_pair_limit(runtime.default_pair_limit)}",
        f"Language: {user.language}",
        f"Worker queues pending: {queue_pending}",
    ]
    for pair in pairs:
        lines.append(
            f"\nPair {pair.pair_id}: {pair.source_id} -> {pair.target_id} | "
            f"scan={format_scan_amount(pair.scan_amount)} | "
            f"post_rule={'ON' if pair.post_rule else 'OFF'} | "
            f"forward_rule={'ON' if pair.forward_rule else 'OFF'}"
        )
    return "\n".join(lines)

def build_ads_list_text(user: UserRecord) -> str:
    lines = []
    for pair in list_user_pairs(user.telegram_user_id):
        if pair.ads_links:
            lines.append(f"Pair {pair.pair_id}: " + ", ".join(pair.ads_links))
    return "\n".join(lines) if lines else "No ads configured."

def build_keyword_list_text(user: UserRecord, pair_id: int, mode: str) -> str:
    pair = get_pair(user.telegram_user_id, pair_id)
    if not pair:
        raise ActionError(f"Pair {pair_id} not found.")
    keywords = pair.ban_keywords if mode == "ban" else pair.post_keywords
    title = "Ban keywords" if mode == "ban" else "Post keywords"
    return f"Pair {pair_id} {title}: " + (", ".join(keywords) if keywords else "-")
