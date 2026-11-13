"""Operations and health endpoints for Annadata Dhwani.

Provides data for the live demo projector dashboard:
- GET /health
- GET /api/ops/calls
- GET /api/ops/dtmf
- POST /api/ops/chaos/flush-redis
- POST /api/admin/clusters/{id}/close-auction
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    return datetime.now(IST).date()


def mask_phone(phone: str | None) -> str:
    """Mask E.164 phone: e.g. +919845012345 -> +91•••••2345."""
    if not phone:
        return "+91•••••0000"
    clean = phone.strip()
    if len(clean) >= 10:
        return f"{clean[:3]}•••••{clean[-4:]}"
    return clean


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    db: str
    redis: str
    tts_clips: int
    price_age_days: int
    provider: str
    public_base_url_ok: bool


class SessionItem(BaseModel):
    phone_masked: str
    kind: str
    state: str
    provider: str
    version: int
    updated_at: str


class JobItem(BaseModel):
    id: Any
    kind: str
    status: str
    attempts: int
    run_at: str


class BreakerItem(BaseModel):
    calls_today: int
    budget: int


class CallsResponse(BaseModel):
    sessions: list[SessionItem]
    jobs: list[JobItem]
    breaker: BreakerItem


class DtmfEventItem(BaseModel):
    session_id: str
    state_before: str
    digits: str
    state_after: str
    dropped_reason: str | None
    at: str


class DtmfResponse(BaseModel):
    events: list[DtmfEventItem]


class FlushRedisResponse(BaseModel):
    ok: bool


class CloseAuctionResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request):
    """System health check for operations dashboard."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)

    # 1. DB Health
    db_status = "error"
    price_age_days = 0
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                db_status = "ok"

                # Calculate price age
                max_price_date = await conn.fetchval(
                    "SELECT MAX(price_date) FROM mandi_prices"
                )
                if max_price_date:
                    price_age_days = max(0, (today_ist() - max_price_date).days)
        except Exception as exc:
            logger.warning("DB health check error: %s", exc)
            db_status = "error"

    # 2. Redis Health
    redis_status = "error"
    if redis_client is not None:
        try:
            res = await redis_client.ping()
            if res:
                redis_status = "ok"
        except Exception as exc:
            logger.warning("Redis health check error: %s", exc)
            redis_status = "error"

    provider = os.environ.get("TELEPHONY_PROVIDER", "sim").lower()
    tts_clips = int(os.environ.get("TTS_CLIPS_COUNT", "220"))

    # Public base URL check
    public_url = os.environ.get("PUBLIC_BASE_URL", "").strip()
    public_base_url_ok = bool(public_url and public_url.startswith("http"))

    return HealthResponse(
        db=db_status,
        redis=redis_status,
        tts_clips=tts_clips,
        price_age_days=price_age_days,
        provider=provider,
        public_base_url_ok=public_base_url_ok if public_url else True,
    )


@router.get("/api/ops/calls", response_model=CallsResponse)
async def get_ops_calls(request: Request):
    """Active call sessions, callback job queue, and circuit breaker status."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)

    now_utc = datetime.now(timezone.utc)
    sessions: list[SessionItem] = []
    jobs: list[JobItem] = []
    calls_today = 0
    budget = int(os.environ.get("DAILY_CALL_BUDGET", "200"))

    # 1. Fetch active sessions from Redis or DB
    if redis_client is not None:
        try:
            # Look up live session keys
            keys = await redis_client.keys("session:*")
            for k in keys[:20]:
                raw = await redis_client.get(k)
                if raw:
                    data = json.loads(raw if isinstance(raw, str) else raw.decode())
                    sessions.append(
                        SessionItem(
                            phone_masked=data.get(
                                "phone_masked",
                                mask_phone(data.get("phone")),
                            ),
                            kind=data.get("kind", "LISTING"),
                            state=data.get("state", "PRICE"),
                            provider=data.get("provider", "sim"),
                            version=int(data.get("version", 1)),
                            updated_at=data.get("updated_at", now_utc.isoformat()),
                        )
                    )
        except Exception as exc:
            logger.warning("Error fetching sessions from Redis: %s", exc)

    if pool is not None:
        try:
            async with pool.acquire() as conn:
                # If no redis sessions, check call_sessions table if it exists
                if not sessions:
                    has_table = await conn.fetchval(
                        "SELECT to_regclass('public.call_sessions')"
                    )
                    if has_table:
                        rows = await conn.fetch(
                            """
                            SELECT phone, phone_masked, kind, state, provider, version, updated_at
                            FROM call_sessions
                            WHERE status IN ('IN_CALL', 'ACTIVE')
                            ORDER BY updated_at DESC LIMIT 20
                            """
                        )
                        for r in rows:
                            pm = r["phone_masked"] or mask_phone(r["phone"])
                            up = (
                                r["updated_at"].isoformat()
                                if hasattr(r["updated_at"], "isoformat")
                                else str(r["updated_at"])
                            )
                            sessions.append(
                                SessionItem(
                                    phone_masked=pm,
                                    kind=r["kind"] or "LISTING",
                                    state=r["state"] or "PRICE",
                                    provider=r["provider"] or "sim",
                                    version=int(r["version"] or 1),
                                    updated_at=up,
                                )
                            )

                # Fetch jobs from call_jobs table if it exists
                has_jobs = await conn.fetchval(
                    "SELECT to_regclass('public.call_jobs')"
                )
                if has_jobs:
                    job_rows = await conn.fetch(
                        """
                        SELECT id, kind, status, attempts, run_at
                        FROM call_jobs
                        ORDER BY id DESC LIMIT 50
                        """
                    )
                    for jr in job_rows:
                        ra = (
                            jr["run_at"].isoformat()
                            if hasattr(jr["run_at"], "isoformat")
                            else str(jr["run_at"])
                        )
                        jobs.append(
                            JobItem(
                                id=jr["id"],
                                kind=jr["kind"] or "CALLBACK",
                                status=jr["status"] or "QUEUED",
                                attempts=int(jr["attempts"] or 0),
                                run_at=ra,
                            )
                        )

                    # Count calls today for breaker
                    today_count = await conn.fetchval(
                        """
                        SELECT count(*) FROM call_jobs
                        WHERE run_at::date = CURRENT_DATE
                          AND status != 'CANCELLED'
                        """
                    )
                    calls_today = int(today_count or 0)

        except Exception as exc:
            logger.warning("Error fetching jobs from DB: %s", exc)

    # Check redis breaker counter if DB count is 0
    if calls_today == 0 and redis_client is not None:
        try:
            today_str = today_ist().isoformat()
            rc = await redis_client.get(f"ops:breaker:{today_str}")
            if rc:
                calls_today = int(rc)
        except Exception:
            pass

    return CallsResponse(
        sessions=sessions,
        jobs=jobs,
        breaker=BreakerItem(calls_today=calls_today, budget=budget),
    )


@router.get("/api/ops/dtmf", response_model=DtmfResponse)
async def get_ops_dtmf(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Recent DTMF events with dropped reason if applicable."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)

    events: list[DtmfEventItem] = []

    if pool is not None:
        try:
            async with pool.acquire() as conn:
                has_table = await conn.fetchval(
                    "SELECT to_regclass('public.dtmf_events')"
                )
                if has_table:
                    rows = await conn.fetch(
                        """
                        SELECT session_id, state_before, digits, state_after, dropped_reason, at
                        FROM dtmf_events
                        ORDER BY at DESC LIMIT $1
                        """,
                        limit,
                    )
                    for r in rows:
                        at_str = (
                            r["at"].isoformat()
                            if hasattr(r["at"], "isoformat")
                            else str(r["at"])
                        )
                        events.append(
                            DtmfEventItem(
                                session_id=str(r["session_id"]),
                                state_before=str(r["state_before"] or ""),
                                digits=str(r["digits"] or ""),
                                state_after=str(r["state_after"] or ""),
                                dropped_reason=r["dropped_reason"],
                                at=at_str,
                            )
                        )
        except Exception as exc:
            logger.warning("Error reading dtmf_events: %s", exc)

    # Fallback to Redis ring buffer if empty
    if not events and redis_client is not None:
        try:
            raw_list = await redis_client.lrange("ops:dtmf:events", 0, limit - 1)
            for item in raw_list:
                d = json.loads(item if isinstance(item, str) else item.decode())
                events.append(
                    DtmfEventItem(
                        session_id=str(d.get("session_id", "")),
                        state_before=str(d.get("state_before", "")),
                        digits=str(d.get("digits", "")),
                        state_after=str(d.get("state_after", "")),
                        dropped_reason=d.get("dropped_reason"),
                        at=str(d.get("at", datetime.now(timezone.utc).isoformat())),
                    )
                )
        except Exception:
            pass

    return DtmfResponse(events=events)


@router.post("/api/ops/chaos/flush-redis", response_model=FlushRedisResponse)
async def flush_redis(request: Request):
    """Chaos testing: flush current Redis database cache."""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "REDIS_UNAVAILABLE", "message": "Redis client not connected"},
        )
    try:
        # flushdb flushes only the selected database (DB 0), not external databases
        await redis_client.flushdb()
        return FlushRedisResponse(ok=True)
    except Exception as exc:
        logger.error("Failed to flush redis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "FLUSH_FAILED", "message": str(exc)},
        )


@router.post(
    "/api/admin/clusters/{cluster_id}/close-auction",
    response_model=CloseAuctionResponse,
)
async def close_auction(cluster_id: str, request: Request):
    """Transition cluster status to CONFIRMING for winning bid settlement."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "DB_UNAVAILABLE", "message": "Database pool not connected"},
        )

    # Validate cluster ID (either UUID or text identifier)
    clean_id = cluster_id.strip()
    try:
        cluster_uuid = uuid.UUID(clean_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "CLUSTER_NOT_FOUND",
                "message": f"Invalid cluster UUID format: {clean_id}",
            },
        )

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Check if cluster exists
                existing = await conn.fetchrow(
                    "SELECT id, status FROM clusters WHERE id = $1 FOR UPDATE",
                    cluster_uuid,
                )
                if not existing:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "error": "CLUSTER_NOT_FOUND",
                            "message": f"Cluster {clean_id} not found",
                        },
                    )

                if existing["status"] in ("CONFIRMING", "ACCEPTED", "CLOSED"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": "AUCTION_ALREADY_CLOSED",
                            "message": f"Cluster {clean_id} auction is already closed or confirming",
                        },
                    )

                # Update status to CONFIRMING
                await conn.execute(
                    "UPDATE clusters SET status = 'CONFIRMING' WHERE id = $1",
                    cluster_uuid,
                )

        return CloseAuctionResponse(status="CONFIRMING")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error closing auction for cluster %s: %s", clean_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "CLOSE_AUCTION_FAILED", "message": str(exc)},
        )
