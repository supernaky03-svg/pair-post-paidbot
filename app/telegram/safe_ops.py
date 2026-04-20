from __future__ import annotations

import asyncio
from typing import Any, Iterable

from telethon.errors import FloodWaitError

async def with_floodwait(fn, *args, **kwargs):
    while True:
        try:
            return await fn(*args, **kwargs)
        except FloodWaitError as e:
            await asyncio.sleep(int(getattr(e, "seconds", 1)) + 1)

async def safe_get_messages(entity, *args, **kwargs):
    from app.telegram.shared_client import client
    return await with_floodwait(client.get_messages, entity, *args, **kwargs)

async def safe_send_message(entity, message: str):
    from app.telegram.shared_client import client
    return await with_floodwait(client.send_message, entity, message)

async def safe_send_file(entity, file, *, caption: str | None = None):
    from app.telegram.shared_client import client
    return await with_floodwait(client.send_file, entity, file, caption=caption)

async def safe_send_album(entity, files: Iterable[Any], captions: list[str] | None = None):
    from app.telegram.shared_client import client
    return await with_floodwait(client.send_file, entity, list(files), caption=captions)

async def safe_get_entity(peer):
    from app.telegram.shared_client import client
    return await with_floodwait(client.get_entity, peer)
