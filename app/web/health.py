from __future__ import annotations

from aiohttp import web

async def healthz(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})

async def start_health_server(port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner
