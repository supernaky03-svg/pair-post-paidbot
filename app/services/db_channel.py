
from __future__ import annotations

import json

from aiogram.exceptions import TelegramBadRequest

from ..core.logging import logger
from ..core.runtime import get_runtime
from ..models import PairRecord, UserRecord
from ..services.entity import build_channel_link
from ..utils.telethon import safe_get_entity


class DatabaseChannelValidationError(ValueError):
    pass


async def validate_database_channel(channel_id: int) -> tuple[int, str]:
    runtime = get_runtime()
    me = await runtime.bot.get_me()
    try:
        chat = await runtime.bot.get_chat(channel_id)
        await runtime.bot.get_chat_member(channel_id, me.id)
    except TelegramBadRequest as exc:
        raise DatabaseChannelValidationError(
            "Bot cannot access this database channel."
        ) from exc

    try:
        await safe_get_entity(int(channel_id))
    except Exception as exc:
        raise DatabaseChannelValidationError(
            "Linked user account cannot access this database channel."
        ) from exc

    if getattr(chat, "type", None) != "channel":
        raise DatabaseChannelValidationError("Database chat must be a private channel.")
    return int(channel_id), getattr(chat, "username", None) and f"https://t.me/{chat.username}" or build_channel_link(channel_id)


async def write_database_event(user: UserRecord, event_type: str, payload: dict) -> None:
    if not user.database_channel_id:
        return
    runtime = get_runtime()
    body = {
        "type": event_type,
        "user_id": user.telegram_user_id,
        "reset_version": user.reset_version,
        "payload": payload,
    }
    text = "<code>" + json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "</code>"
    chunks: list[str] = []
    while text:
        chunks.append(text[:3500])
        text = text[3500:]
    for chunk in chunks:
        try:
            await runtime.bot.send_message(user.database_channel_id, chunk)
        except Exception:
            logger.exception(
                "Failed to write database channel event for user=%s", user.telegram_user_id
            )
            return


async def mirror_user_snapshot(user: UserRecord, pairs: list[PairRecord]) -> None:
    payload = {
        "user": {
            "language": user.language,
            "database_channel_id": user.database_channel_id,
            "database_channel_link": user.database_channel_link,
            "access_expires_at": user.access_expires_at.isoformat() if user.access_expires_at else None,
            "pair_limit": user.pair_limit,
            "restore_mode": user.restore_mode,
            "reset_version": user.reset_version,
        },
        "pairs": [
            {
                "pair_id": pair.pair_id,
                "source_id": pair.source_id,
                "target_id": pair.target_id,
                "source_chat_id": pair.source_chat_id,
                "target_chat_id": pair.target_chat_id,
                "last_processed_id": pair.last_processed_id,
                "forward_rule": pair.forward_rule,
                "post_rule": pair.post_rule,
                "scan_amount": pair.scan_amount,
                "ads_links": pair.ads_links,
                "ban_keywords": pair.ban_keywords,
                "post_keywords": pair.post_keywords,
            }
            for pair in pairs
        ],
    }
    await write_database_event(user, "snapshot", payload)
