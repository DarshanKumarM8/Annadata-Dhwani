"""Pricing helpers for Annadata Dhwani."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from statistics import median

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    """Return today's date in IST."""
    return datetime.now(IST).date()


def compute_afpp(
    modal: float,
    pct_deduction: float,
    transport: float,
    handling: float,
) -> int:
    """Adjusted Fair Procurement Price, floored to nearest ₹10."""
    raw = modal * (1 - pct_deduction) - transport - handling
    return int(raw // 10 * 10)


def safe_median(values: list[float]) -> float | None:
    """Median that returns None for an empty list instead of raising."""
    return median(values) if values else None


def filter_outliers(modals: list[float]) -> list[float]:
    """Drop modals more than 40 % away from the group median."""
    if not modals:
        return []
    med = median(modals)
    if med <= 0:
        return list(modals)
    return [m for m in modals if abs(m - med) / med <= 0.4]


async def get_floor(
    pool,
    redis,
    district_code: str,
    crop_code: str,
) -> dict | None:
    """Look up the current AFPP price floor.

    Lookup order
    ------------
    1. Redis key ``floor:{district_code}:{crop_code}`` (JSON)
    2. ``price_floors`` row where ``as_of`` = today (IST)
    3. Newest ``price_floors`` row with ``as_of`` within 7 days
    4. ``None``

    Never raises – logs and returns *None* on any error.
    """
    try:
        key = f"floor:{district_code}:{crop_code}"

        # 1) Redis cache
        if redis is not None:
            try:
                cached = await redis.get(key)
                if cached is not None:
                    if isinstance(cached, dict):
                        return cached
                    if isinstance(cached, (bytes, bytearray)):
                        cached = cached.decode("utf-8")
                    return json.loads(cached)
            except Exception:
                logger.warning("Redis lookup error for %s", key)

        if pool is None:
            return None

        today = today_ist()

        async with pool.acquire() as conn:
            # 2) Today's floor
            row = await conn.fetchrow(
                "SELECT modal_price, afpp, basis, price_date "
                "FROM price_floors "
                "WHERE district_code = $1 AND crop_code = $2 AND as_of = $3",
                district_code,
                crop_code,
                today,
            )
            if row:
                price_date_val = row["price_date"]
                price_date_str = (
                    price_date_val.isoformat()
                    if hasattr(price_date_val, "isoformat")
                    else str(price_date_val)
                )
                result = {
                    "modal_price": float(row["modal_price"]),
                    "afpp": int(row["afpp"]),
                    "basis": str(row["basis"]),
                    "price_date": price_date_str,
                }
                if redis is not None:
                    try:
                        await redis.set(key, json.dumps(result), ex=93600)
                    except Exception:
                        pass
                return result

            # 3) Newest within 7 days
            row = await conn.fetchrow(
                "SELECT modal_price, afpp, basis, price_date "
                "FROM price_floors "
                "WHERE district_code = $1 AND crop_code = $2 "
                "AND as_of >= $3 "
                "ORDER BY as_of DESC LIMIT 1",
                district_code,
                crop_code,
                today - timedelta(days=7),
            )
            if row:
                price_date_val = row["price_date"]
                price_date_str = (
                    price_date_val.isoformat()
                    if hasattr(price_date_val, "isoformat")
                    else str(price_date_val)
                )
                return {
                    "modal_price": float(row["modal_price"]),
                    "afpp": int(row["afpp"]),
                    "basis": str(row["basis"]),
                    "price_date": price_date_str,
                }

        # 4) Nothing found
        return None

    except Exception:
        logger.exception("get_floor failed for %s/%s", district_code, crop_code)
        return None


async def refresh(pool, redis, live: bool = True) -> int:
    """Trigger price ingestion to refresh price floors.

    Returns the number of floors written.
    """
    import importlib
    import os
    from pathlib import Path
    try:
        try:                                               # the server runs from backend/, scripts/ is a plain folder there
            ingest = importlib.import_module("scripts.ingest_prices")
        except ImportError:
            ingest = importlib.import_module("ingest_prices")
        import asyncio
        stored_basis = ("DISTRICT_FRESH", "DISTRICT_7D", "STATE_7D")    # a failed fetch returns NO_DATA entries that were not stored
        floors: list = []
        key = os.getenv("DATA_GOV_KEY", "")
        if key and live:                                   # live Agmarknet data first, but never wait more than 30 s for it
            try:
                res = await asyncio.wait_for(ingest.ingest_prices(pool, redis, api_key=key), timeout=30)
                floors = [f for f in res if f.get("basis") in stored_basis]
            except Exception:
                logger.warning("live price fetch failed, using the saved samples", exc_info=True)
        if not floors:                                     # offline: the saved Agmarknet samples in contracts/fixtures
            fixtures = str(Path(__file__).resolve().parents[3] / "contracts" / "fixtures")
            res = await ingest.ingest_prices(pool, redis, fixtures_dir=fixtures)
            floors = [f for f in res if f.get("basis") in stored_basis]
        return len(floors)
    except Exception:
        logger.exception("prices refresh failed")
        return 0

