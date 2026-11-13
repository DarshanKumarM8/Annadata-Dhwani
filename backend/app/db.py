"""asyncpg pool, created once at start-up. Owner: Darshan."""
import json

import asyncpg

from .config import settings

pool: asyncpg.Pool | None = None


async def _init(conn: asyncpg.Connection) -> None:
    # jsonb <-> python objects
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def connect() -> asyncpg.Pool:
    global pool
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10, init=_init)
    return pool


async def close() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None
