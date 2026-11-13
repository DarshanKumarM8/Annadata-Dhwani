"""Ops and chaos endpoints. Owner: Darshan. D5 adds admin auth and the /api/ops/calls and /dtmf readers."""
from fastapi import APIRouter, HTTPException

from .. import cache
from ..config import settings

router = APIRouter(prefix="/api/ops")


@router.post("/chaos/flush-redis")
async def flush_redis():
    """Demo failure injection: wipe Valkey. Live calls must carry on from the Postgres checkpoint."""
    if not settings.demo_mode:
        raise HTTPException(403, detail={"error": "DEMO_MODE_ONLY"})
    await cache.redis.flushall()
    cache.load_scripts()
    return {"ok": True}
