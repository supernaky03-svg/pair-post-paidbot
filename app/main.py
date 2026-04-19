
import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from telethon import TelegramClient
from telethon.sessions import StringSession

from .bot.router import build_router
from .core.config import Settings, load_settings
from .core.logging import setup_logging, logger
from .core.runtime import AppRuntime, set_runtime, warm_runtime_cache
from .db.database import Database
from .services.worker import (
    register_telethon_handlers,
    start_periodic_scanner,
    stop_periodic_scanner,
)
from .services.health import start_health_server


async def main() -> None:
    settings: Settings = load_settings()
    setup_logging(settings.log_level)

    db = Database(settings.database_url)
    await db.apply_schema()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    if not settings.telethon_session_string:
        raise RuntimeError(
            "TELETHON_SESSION_STRING is required for production deployment."
        )

    telethon_client = TelegramClient(
        StringSession(settings.telethon_session_string),
        settings.api_id,
        settings.api_hash,
        auto_reconnect=True,
    )
    await telethon_client.connect()
    if not await telethon_client.is_user_authorized():
        raise RuntimeError(
            "Telethon session is not authorized. Generate a valid session string first."
        )

    runtime = AppRuntime(
        settings=settings,
        db=db,
        bot=bot,
        dp=dp,
        telethon=telethon_client,
    )
    set_runtime(runtime)
    await warm_runtime_cache()

    dp.include_router(build_router())
    register_telethon_handlers(runtime)

    web_runner = await start_health_server(runtime)
    poll_task = asyncio.create_task(start_periodic_scanner(runtime))
    telethon_task = asyncio.create_task(telethon_client.run_until_disconnected())
    bot_task = asyncio.create_task(dp.start_polling(bot))

    logger.info("Application started successfully")

    done, pending = await asyncio.wait(
        {poll_task, telethon_task, bot_task},
        return_when=asyncio.FIRST_EXCEPTION,
    )
    for task in done:
        exc = task.exception()
        if exc:
            raise exc
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    await stop_periodic_scanner(runtime)
    await bot.session.close()
    await telethon_client.disconnect()
    await web_runner.cleanup()


def run() -> None:
    asyncio.run(main())
