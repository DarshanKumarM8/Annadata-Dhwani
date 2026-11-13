"""Price endpoints for Annadata Dhwani.

Provides:
- GET /api/prices/today: Current AFPP floors for all crops & districts
- GET /api/prices/floor: AFPP floor lookup for a given district and crop
- GET /api/prices/history: Historical mandi arrival prices
- POST /api/ops/ingest-prices: Trigger price ingestion (live or from fixtures)
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from backend.app.services.pricing import get_floor, today_ist

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class FloorResponse(BaseModel):
    district_code: str
    crop_code: str
    modal_price: float
    afpp: int
    basis: str
    price_date: str


class MandiHistoryItem(BaseModel):
    market: str
    price_date: str
    min_price: float | None
    max_price: float | None
    modal_price: float
    source: str


class IngestRequest(BaseModel):
    from_fixtures: str | None = None


class IngestSummaryItem(BaseModel):
    district_code: str
    crop_code: str
    modal_price: float | None
    afpp: int | None
    basis: str
    price_date: str | None


class IngestResponse(BaseModel):
    success: bool
    results: list[IngestSummaryItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/prices/floor", response_model=FloorResponse)
async def get_price_floor(
    request: Request,
    district_code: str = Query(..., description="District code e.g. KA-MANDYA"),
    crop_code: str = Query(..., description="Crop code e.g. ragi"),
):
    """Get the current AFPP price floor for a crop in a district."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)

    floor = await get_floor(pool, redis_client, district_code, crop_code)
    if not floor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Price floor not found for {district_code} / {crop_code}",
        )

    return FloorResponse(
        district_code=district_code,
        crop_code=crop_code,
        modal_price=floor["modal_price"],
        afpp=floor["afpp"],
        basis=floor["basis"],
        price_date=floor["price_date"],
    )


@router.get("/api/prices/today", response_model=list[FloorResponse])
async def get_today_floors(request: Request):
    """List current active price floors across all districts and crops."""
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    today = today_ist()
    try:
        async with pool.acquire() as conn:
            # Fetch latest price floors within 7 days
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (district_code, crop_code)
                    district_code, crop_code, modal_price, afpp, basis, price_date
                FROM price_floors
                WHERE as_of >= $1
                ORDER BY district_code, crop_code, as_of DESC
                """,
                today - timedelta(days=7),
            )
            return [
                FloorResponse(
                    district_code=r["district_code"],
                    crop_code=r["crop_code"],
                    modal_price=float(r["modal_price"]),
                    afpp=int(r["afpp"]),
                    basis=str(r["basis"]),
                    price_date=(
                        r["price_date"].isoformat()
                        if hasattr(r["price_date"], "isoformat")
                        else str(r["price_date"])
                    ),
                )
                for r in rows
            ]
    except Exception as exc:
        logger.exception("Error fetching today floors: %s", exc)
        # Return 503 for connection or database failures
        if isinstance(exc, (ConnectionError, OSError)) or "connection" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving price floors",
        )


@router.get("/api/prices/history", response_model=list[MandiHistoryItem])
async def get_price_history(
    request: Request,
    district_code: str = Query(...),
    crop_code: str = Query(...),
    days: int = Query(7, ge=1, le=90),
):
    """Retrieve historical mandi price records for a crop and district."""
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    today = today_ist()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT market, price_date, min_price, max_price, modal_price, source
                FROM mandi_prices
                WHERE district_code = $1 AND crop_code = $2
                  AND price_date >= $3
                ORDER BY price_date DESC, market ASC
                """,
                district_code,
                crop_code,
                today - timedelta(days=days),
            )
            return [
                MandiHistoryItem(
                    market=r["market"],
                    price_date=(
                        r["price_date"].isoformat()
                        if hasattr(r["price_date"], "isoformat")
                        else str(r["price_date"])
                    ),
                    min_price=float(r["min_price"]) if r["min_price"] is not None else None,
                    max_price=float(r["max_price"]) if r["max_price"] is not None else None,
                    modal_price=float(r["modal_price"]),
                    source=r["source"],
                )
                for r in rows
            ]
    except Exception as exc:
        logger.exception("Error fetching price history: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving price history",
        )


@router.post("/api/ops/ingest-prices", response_model=IngestResponse)
async def trigger_price_ingestion(request: Request, payload: IngestRequest | None = None):
    """Trigger mandi price ingestion via API (from data.gov.in or fixtures)."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )

    fixtures_dir = payload.from_fixtures if payload else None
    if not fixtures_dir:
        # Check default contracts/fixtures directory
        default_fix = Path("contracts/fixtures")
        if default_fix.exists() and any(default_fix.glob("agmark_*.json")):
            fixtures_dir = str(default_fix)

    api_key = os.environ.get("DATA_GOV_KEY", "")

    try:
        from backend.scripts.ingest_prices import ingest_prices

        results = await ingest_prices(
            pool=pool,
            rds=redis_client,
            api_key=api_key,
            fixtures_dir=fixtures_dir,
        )
        return IngestResponse(
            success=True,
            results=[
                IngestSummaryItem(
                    district_code=r["district_code"],
                    crop_code=r["crop_code"],
                    modal_price=r["modal_price"],
                    afpp=r["afpp"],
                    basis=r["basis"],
                    price_date=r["price_date"],
                )
                for r in results
            ],
        )
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Price ingestion failed: {exc}",
        )
