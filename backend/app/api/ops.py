"""Admin, ops and chaos endpoints (role admin). Owner: Darshan."""
import time

import asyncpg
from fastapi import APIRouter, Depends

from .. import cache, db
from ..config import settings
from ..services import bidding
from .auth import ApiError, require

router = APIRouter(prefix="/api")
admin = Depends(require("admin"))


def mask(phone: str) -> str:
    return "+91•••••" + phone[-4:]


@router.post("/ops/chaos/flush-redis")
async def flush_redis(_: dict = admin):
    """Demo failure injection: wipe Valkey. Live calls must carry on from the Postgres checkpoint."""
    if not settings.demo_mode:
        raise ApiError(403, "DEMO_MODE_ONLY")
    await cache.redis.flushdb()
    cache.load_scripts()
    return {"ok": True}


@router.get("/ops/calls")
async def ops_calls(_: dict = admin):
    sessions = await db.pool.fetch("""SELECT phone, kind, state, provider, version, updated_at FROM call_sessions
        WHERE ended_at IS NULL AND updated_at > now() - interval '30 minutes' ORDER BY updated_at DESC LIMIT 50""")
    jobs = await db.pool.fetch("""SELECT id::text, kind, status, attempts, run_at FROM call_jobs
        WHERE status IN ('QUEUED','DIALING','IN_CALL') ORDER BY run_at LIMIT 50""")
    used = int(await cache.redis.get(f"budget:calls:{time.strftime('%Y%m%d')}") or 0)
    return {"sessions": [{"phone_masked": mask(s["phone"]), "kind": s["kind"], "state": s["state"],
                          "provider": s["provider"], "version": s["version"], "updated_at": s["updated_at"].isoformat()}
                         for s in sessions],
            "jobs": [{**dict(j), "run_at": j["run_at"].isoformat()} for j in jobs],
            "breaker": {"calls_today": used, "budget": settings.daily_call_budget}}


@router.get("/ops/dtmf")
async def ops_dtmf(limit: int = 50, _: dict = admin):
    rows = await db.pool.fetch("""SELECT session_id::text, state_before, digits, state_after, dropped_reason, at
                                  FROM dtmf_events ORDER BY id DESC LIMIT $1""", max(1, min(limit, 200)))
    return {"events": [{**dict(r), "at": r["at"].isoformat()} for r in rows]}


@router.post("/admin/clusters/{cid}/close-auction")
async def close_auction(cid: str, _: dict = admin):
    try:
        status = await bidding.close_auction(db.pool, cid)
    except asyncpg.DataError:
        status = None
    if status is None:
        raise ApiError(404, "NOT_FOUND")
    return {"status": status}


@router.post("/admin/clusters/{cid}/simulate-farmers")
async def simulate_farmers(cid: str, body: dict | None = None, _: dict = admin):
    """DEMO ONLY: stands in for the farmers' accept/reject calls. Body: {"accept": true, "accepted_lots": 3}."""
    if not settings.demo_mode:
        raise ApiError(403, "DEMO_MODE_ONLY")
    body = body or {}
    try:
        return await bidding.simulate_farmers(db.pool, cid, bool(body.get("accept", True)), body.get("accepted_lots"))
    except asyncpg.DataError:
        raise ApiError(404, "NOT_FOUND")


@router.post("/admin/prices/refresh")
async def prices_refresh(_: dict = admin):
    try:
        from ..services import pricing                       # Anirudh's module, when merged
        return {"floors_written": await pricing.refresh(db.pool, cache.redis)}
    except ImportError:
        return {"floors_written": 0, "note": "pricing module not merged yet"}
