
from __future__ import annotations

from aiohttp import web

from ..core.logging import logger
from ..core.runtime import AppRuntime


async def health_handler(request: web.Request) -> web.Response:
    runtime: AppRuntime = request.app["runtime"]
    return web.json_response(
        {
            "ok": True,
            "users": len(runtime.users),
            "pairs": sum(len(items) for items in runtime.pairs_by_user.values()),
        }
    )


async def root_handler(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def start_health_server(runtime: AppRuntime) -> web.AppRunner:
    app = web.Application()
    app["runtime"] = runtime
    app.router.add_get("/", root_handler)
    app.router.add_get(runtime.settings.health_path, health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, runtime.settings.host, runtime.settings.port)
    await site.start()
    logger.info("Health server started at %s:%s", runtime.settings.host, runtime.settings.port)
    return runner
