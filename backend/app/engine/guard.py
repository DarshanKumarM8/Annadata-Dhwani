"""Reliability gates in Valkey: missed-call dedupe and limits, per-farmer call lock, event idempotency. Owner: Darshan.

Keys (contract C10): miss:{phone} 20 s, rl:cb:{phone}:10m / :day, budget:calls:{yyyymmdd}, lock:call:{phone} 300 s,
evt:{call_id}:{event_id} 3600 s. Correctness never depends on the lock: it only stops two simultaneous calls to one
farmer. Listings and bids are protected by Postgres constraints.
"""
import time

from .. import cache
from ..config import settings

LOCK_MS = 300_000


async def accept_missed_call(phone: str, limit_10m: int | None = None, limit_day: int | None = None) -> str:
    """'ok' | 'DUPLICATE' (same number within 20 s) | 'RATE_LIMITED' (3 per 10 min, 6 per day) | 'BUDGET'."""
    r = cache.redis
    if not await r.set(f"miss:{phone}", "1", nx=True, ex=20):
        return "DUPLICATE"
    res = await cache.scripts["allow_callback"](
        keys=[f"rl:cb:{phone}:10m", f"rl:cb:{phone}:day", f"budget:calls:{time.strftime('%Y%m%d')}"],
        args=[limit_10m or settings.cb_limit_10m, limit_day or settings.cb_limit_day, settings.daily_call_budget])
    return {1: "ok", 0: "RATE_LIMITED", -1: "BUDGET"}[int(res)]


async def acquire_lock(phone: str, token: str) -> bool:
    return bool(await cache.redis.set(f"lock:call:{phone}", token, nx=True, px=LOCK_MS))


async def extend_lock(phone: str, token: str) -> None:
    k = f"lock:call:{phone}"
    if await cache.redis.get(k) == token:
        await cache.redis.pexpire(k, LOCK_MS)


async def release_lock(phone: str, token: str) -> None:
    await cache.scripts["release_lock"](keys=[f"lock:call:{phone}"], args=[token])


async def is_duplicate_event(call_id: str, event_id: str) -> bool:
    """True if this provider event was already applied (webhook retry). Marks it as seen otherwise."""
    return not await cache.redis.set(f"evt:{call_id}:{event_id}", "1", nx=True, ex=3600)
