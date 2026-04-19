
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher
from telethon import TelegramClient

from ..core.config import Settings
from ..core.logging import logger
from ..db.database import Database
from ..models import PairRecord, UserRecord


@dataclass(slots=True)
class PairRuntime:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    source_entity: object | None = None
    target_entity: object | None = None
    source_chat_id: int | None = None
    target_chat_id: int | None = None
    last_sent_grouped_ids: set[int] = field(default_factory=set)


@dataclass(slots=True)
class AppRuntime:
    settings: Settings
    db: Database
    bot: Bot
    dp: Dispatcher
    telethon: TelegramClient
    users: Dict[int, UserRecord] = field(default_factory=dict)
    pairs_by_user: Dict[int, Dict[int, PairRecord]] = field(default_factory=dict)
    pairs_by_source: Dict[int, List[Tuple[int, int]]] = field(default_factory=dict)
    pair_runtime: Dict[Tuple[int, int], PairRuntime] = field(default_factory=dict)
    default_pair_limit: int = 20
    poll_stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    source_queue_manager: object | None = None


_RUNTIME: Optional[AppRuntime] = None


def set_runtime(runtime: AppRuntime) -> None:
    global _RUNTIME
    _RUNTIME = runtime


def get_runtime() -> AppRuntime:
    if _RUNTIME is None:
        raise RuntimeError("Runtime has not been initialized yet")
    return _RUNTIME


async def warm_runtime_cache() -> None:
    runtime = get_runtime()
    runtime.default_pair_limit = await runtime.db.get_global_pair_limit(
        runtime.settings.default_pair_limit
    )
    for user in await runtime.db.list_users():
        cache_user(user)
    for pair in await runtime.db.list_pairs():
        cache_pair(pair)
    logger.info(
        "Runtime cache warmed: users=%s pairs=%s default_pair_limit=%s",
        len(runtime.users),
        sum(len(pairs) for pairs in runtime.pairs_by_user.values()),
        runtime.default_pair_limit,
    )


def cache_user(user: UserRecord) -> None:
    runtime = get_runtime()
    runtime.users[user.telegram_user_id] = user
    runtime.pairs_by_user.setdefault(user.telegram_user_id, {})


def get_user(user_id: int) -> UserRecord | None:
    return get_runtime().users.get(int(user_id))


def cache_pair(pair: PairRecord) -> None:
    runtime = get_runtime()
    runtime.pairs_by_user.setdefault(pair.owner_user_id, {})
    runtime.pairs_by_user[pair.owner_user_id][pair.pair_id] = pair
    _rebuild_source_index_for_pair(pair)


def _remove_pair_from_source_index(user_id: int, pair_id: int) -> None:
    runtime = get_runtime()
    for source_chat_id, refs in list(runtime.pairs_by_source.items()):
        runtime.pairs_by_source[source_chat_id] = [
            ref for ref in refs if ref != (user_id, pair_id)
        ]
        if not runtime.pairs_by_source[source_chat_id]:
            runtime.pairs_by_source.pop(source_chat_id, None)


def _rebuild_source_index_for_pair(pair: PairRecord) -> None:
    runtime = get_runtime()
    _remove_pair_from_source_index(pair.owner_user_id, pair.pair_id)
    if pair.source_chat_id is None:
        return
    refs = runtime.pairs_by_source.setdefault(pair.source_chat_id, [])
    if (pair.owner_user_id, pair.pair_id) not in refs:
        refs.append((pair.owner_user_id, pair.pair_id))


def remove_pair(user_id: int, pair_id: int) -> None:
    runtime = get_runtime()
    user_pairs = runtime.pairs_by_user.get(int(user_id), {})
    user_pairs.pop(int(pair_id), None)
    _remove_pair_from_source_index(int(user_id), int(pair_id))
    runtime.pair_runtime.pop((int(user_id), int(pair_id)), None)


def clear_user_pairs(user_id: int) -> None:
    runtime = get_runtime()
    for pair_id in list(runtime.pairs_by_user.get(int(user_id), {}).keys()):
        remove_pair(int(user_id), int(pair_id))
    runtime.pairs_by_user[int(user_id)] = {}


def get_pair(user_id: int, pair_id: int) -> PairRecord | None:
    return get_runtime().pairs_by_user.get(int(user_id), {}).get(int(pair_id))


def list_user_pairs(user_id: int) -> List[PairRecord]:
    return sorted(
        get_runtime().pairs_by_user.get(int(user_id), {}).values(),
        key=lambda item: item.pair_id,
    )


def get_pairs_for_source_chat(source_chat_id: int) -> List[PairRecord]:
    runtime = get_runtime()
    pairs: List[PairRecord] = []
    for user_id, pair_id in runtime.pairs_by_source.get(int(source_chat_id), []):
        pair = get_pair(user_id, pair_id)
        user = get_user(user_id)
        if not pair or not user or user.is_banned or not user.has_access():
            continue
        pairs.append(pair)
    return pairs


def get_pair_runtime(user_id: int, pair_id: int) -> PairRuntime:
    runtime = get_runtime()
    key = (int(user_id), int(pair_id))
    if key not in runtime.pair_runtime:
        runtime.pair_runtime[key] = PairRuntime()
    return runtime.pair_runtime[key]
