"""Session store in Valkey with compare-and-set (lua/session_cas.lua). Owner: Darshan.

D3 adds the Postgres checkpoint and rehydrate on a Redis miss.
"""
import json

from .. import cache
from ..config import settings


class SessionConflict(Exception):
    """Another handler wrote the session first (stale version)."""


def key(phone: str) -> str:
    return f"sess:{phone}"


async def load(phone: str) -> dict | None:
    raw = await cache.redis.get(key(phone))
    return json.loads(raw) if raw else None


async def save(s: dict, expected_version: int) -> None:
    """Write s with version expected_version+1; raises SessionConflict if someone else moved first."""
    s["version"] = expected_version + 1
    res = await cache.scripts["session_cas"](
        keys=[key(s["phone"])], args=[expected_version, json.dumps(s), settings.session_ttl_s])
    if res == 1:
        return
    if res == -1 and expected_version != 0:
        # session vanished (TTL, FLUSHALL): treat as a fresh write rather than failing the caller's call
        await cache.redis.set(key(s["phone"]), json.dumps(s), ex=settings.session_ttl_s)
        return
    raise SessionConflict(s["phone"])
