from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings


pool = AsyncConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=5,
    kwargs={
        "sslmode": "require",
        "row_factory": dict_row,
    },
    open=False,
)


async def open_pool() -> None:
    if pool.closed:
        await pool.open()


async def close_pool() -> None:
    if not pool.closed:
        await pool.close()


@asynccontextmanager
async def get_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    await open_pool()
    async with pool.connection() as conn:
        yield conn


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
