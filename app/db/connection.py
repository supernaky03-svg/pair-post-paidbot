from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings

@asynccontextmanager
async def get_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    conn = await psycopg.AsyncConnection.connect(settings.database_url, sslmode="require", row_factory=dict_row)
    try:
        yield conn
    finally:
        await conn.close()

async def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()

async def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()

async def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
        await conn.commit()
