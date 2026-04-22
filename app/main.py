from __future__ import annotations

from aiogram import Bot, Dispatcher

from app.bot.handlers import router, runtime_manager
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.connection import close_pool, open_pool
from app.db.migrations import migrate
from app.services.session_reconcile import SessionReconcileService
from app.telegram.shared_client import client
from app.web.health import start_health_server


async def main() -> None:
    setup_logging()
    await open_pool()
    await migrate()

    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)

    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError(
            "TELETHON_SESSION_STRING / SESSION_STRING is not authorized. "
            "Generate a valid shared Telethon StringSession first."
        )

    reconcile_service = SessionReconcileService()
    await reconcile_service.run(bot)

    await runtime_manager.start()
    health_runner = await start_health_server(settings.health_port)
    logger.info("Bot + runtime started.")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await runtime_manager.stop()
        await client.disconnect()
        await close_pool()
        await bot.session.close()
        await health_runner.cleanup()
        
