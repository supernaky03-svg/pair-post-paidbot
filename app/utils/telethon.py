from __future__ import annotations

import asyncio
from typing import Any

from telethon.errors import FloodWaitError

from ..core.logging import logger
from ..core.runtime import get_runtime


async def run_with_floodwait(coro_factory, *args, **kwargs):
    while True:
        try:
            return await coro_factory(*args, **kwargs)
        except FloodWaitError as exc:
            seconds = int(getattr(exc, "seconds", 0))
            logger.warning("FloodWait detected. Sleeping %s seconds.", seconds)
            await asyncio.sleep(seconds + 1)


async def safe_get_entity(entity_like: Any):
    runtime = get_runtime()
    return await run_with_floodwait(runtime.telethon.get_entity, entity_like)


async def get_linked_account_label() -> str:
    runtime = get_runtime()
    me = await run_with_floodwait(runtime.telethon.get_me)

    username = getattr(me, "username", None)
    first_name = getattr(me, "first_name", "") or ""
    last_name = getattr(me, "last_name", "") or ""
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()

    if username:
        if full_name:
            return f"@{username} ({full_name})"
        return f"@{username}"

    if full_name:
        return f"{full_name} | ID: {me.id}"

    return f"ID: {me.id}"


async def safe_get_message(chat: Any, msg_id: int):
    runtime = get_runtime()
    return await run_with_floodwait(runtime.telethon.get_messages, chat, ids=msg_id)


async def safe_get_messages(chat: Any, limit: int):
    runtime = get_runtime()
    return await run_with_floodwait(runtime.telethon.get_messages, chat, limit=limit)


async def safe_send_message(chat: Any, message: str):
    runtime = get_runtime()
    return await run_with_floodwait(runtime.telethon.send_message, chat, message=message)


async def safe_send_file(chat: Any, file: Any, caption=None, force_document=False):
    runtime = get_runtime()
    return await run_with_floodwait(
        runtime.telethon.send_file,
        chat,
        file=file,
        caption=caption,
        force_document=force_document,
    )


async def safe_send_album(chat: Any, files: list[Any], captions=None):
    runtime = get_runtime()
    return await run_with_floodwait(runtime.telethon.send_file, chat, file=files, caption=captions)
