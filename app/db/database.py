
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def apply_schema(self) -> None:
        schema = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")
        async with await psycopg.AsyncConnection.connect(
            self.dsn,
            sslmode="require",
            row_factory=dict_row,
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(schema)
            await conn.commit()

    async def fetch(self, query: str, params: Sequence[Any] | None = None) -> list[dict]:
        async with await psycopg.AsyncConnection.connect(
            self.dsn,
            sslmode="require",
            row_factory=dict_row,
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params or [])
                return await cur.fetchall()

    async def fetchrow(
        self, query: str, params: Sequence[Any] | None = None
    ) -> dict | None:
        async with await psycopg.AsyncConnection.connect(
            self.dsn,
            sslmode="require",
            row_factory=dict_row,
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params or [])
                return await cur.fetchone()

    async def execute(self, query: str, params: Sequence[Any] | None = None) -> None:
        async with await psycopg.AsyncConnection.connect(
            self.dsn,
            sslmode="require",
            row_factory=dict_row,
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params or [])
            await conn.commit()

    async def executemany(self, query: str, params_seq: Iterable[Sequence[Any]]) -> None:
        async with await psycopg.AsyncConnection.connect(
            self.dsn,
            sslmode="require",
            row_factory=dict_row,
        ) as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_seq)
            await conn.commit()

    async def get_global_pair_limit(self, default: int) -> int:
        row = await self.fetchrow(
            "SELECT value FROM app_settings WHERE key = 'default_pair_limit'"
        )
        if not row:
            return int(default)
        try:
            return int(row["value"])
        except Exception:
            return int(default)
