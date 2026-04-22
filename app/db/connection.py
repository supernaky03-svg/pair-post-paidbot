from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable, TypeVar

import psycopg
from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

T = TypeVar("T")

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


async def _refresh_pool_after_operational_error() -> None:
    """Best-effort recovery for stale/broken pooled SSL connections."""
    await open_pool()
    try:
        await pool.check()
        return
    except Exception:
        pass

    try:
        await pool.close()
    except Exception:
        pass

    # Small pause to avoid immediate reuse of a bad socket state.
    await asyncio.sleep(0.2)
    await pool.open()


async def _run_with_retry(fn: Callable[[], Awaitable[T]]) -> T:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return await fn()
        except OperationalError as exc:
            last_exc = exc
            if attempt == 1:
                raise
            await _refresh_pool_after_operational_error()
    assert last_exc is not None
    raise last_exc


@asynccontextmanager
async def get_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    await open_pool()
    async with pool.connection() as conn:
        yield conn


async def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    async def _op() -> list[dict[str, Any]]:
        async with get_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

    return await _run_with_retry(_op)


async def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    async def _op() -> dict[str, Any] | None:
        async with get_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

    return await _run_with_retry(_op)


async def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    async def _op() -> None:
        async with get_conn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
            await conn.commit()

    await _run_with_retry(_op)
    
