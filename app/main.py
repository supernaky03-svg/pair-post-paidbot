from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers import router, runtime_manager
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.migrations import migrate
from app.telegram.shared_client import client
from app.web.health import start_health_server

async def main() -> None:
    setup_logging()
    await migrate()
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("SESSION_STRING is not authorized. Generate a valid shared Telethon StringSession first.")
    await runtime_manager.start()
    health_runner = await start_health_server(settings.health_port)
    logger.info("Bot + runtime started.")
    try:
        await dp.start_polling(bot)
    finally:
        await runtime_manager.stop()
        await client.disconnect()
        await health_runner.cleanup()
