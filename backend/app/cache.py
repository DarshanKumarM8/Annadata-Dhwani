"""Valkey/Redis client and Lua script registry. Owner: Darshan."""
from pathlib import Path

import redis.asyncio as aioredis

from .config import settings

LUA_DIR = Path(__file__).parent / "lua"

redis: aioredis.Redis | None = None
scripts: dict[str, object] = {}


async def connect() -> aioredis.Redis:
    global redis
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    load_scripts()
    return redis


def load_scripts() -> None:
    """(Re)register Lua scripts. Called again after a FLUSHALL because registered SHAs are gone."""
    assert redis is not None
    for f in LUA_DIR.glob("*.lua"):
        scripts[f.stem] = redis.register_script(f.read_text(encoding="utf-8"))


async def close() -> None:
    global redis
    if redis:
        await redis.aclose()
        redis = None
