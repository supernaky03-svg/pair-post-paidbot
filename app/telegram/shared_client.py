from __future__ import annotations

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.config import settings

client = TelegramClient(StringSession(settings.session_string), settings.api_id, settings.api_hash)
