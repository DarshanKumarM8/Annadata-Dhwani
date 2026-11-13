"""Unit tests for pricing service and helpers."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
import sys

import pytest

# Ensure backend/app/services is on sys.path
_services = str(Path(__file__).resolve().parent.parent / "app" / "services")
if _services not in sys.path:
    sys.path.insert(0, _services)

from pricing import (
    compute_afpp,
    filter_outliers,
    get_floor,
    safe_median,
    today_ist,
)


# ---- 1. AFPP calculation tests --------------------------------------------


def test_compute_afpp_acceptance_spec():
    """Verify acceptance criteria: compute_afpp(3565, 0.02, 50, 10) == 3430."""
    result = compute_afpp(3565, 0.02, 50, 10)
    assert result == 3430
    assert isinstance(result, int)


def test_compute_afpp_rounding_and_edge_cases():
    """Verify flooring to nearest multiple of 10."""
    # 2000 * (1 - 0.05) - 30 - 10 = 1900 - 40 = 1860
    assert compute_afpp(2000, 0.05, 30, 10) == 1860

    # Flooring down: 1007 -> 1000
    assert compute_afpp(1007, 0.0, 0, 0) == 1000
    # 1009.9 -> 1000
    assert compute_afpp(1009.9, 0.0, 0, 0) == 1000
    # Zero deductions
    assert compute_afpp(5205, 0.0, 0, 0) == 5200


# ---- 2. Median and outlier helpers ----------------------------------------


def test_safe_median():
    assert safe_median([]) is None
    assert safe_median([100.0]) == 100.0
    assert safe_median([100.0, 200.0]) == 150.0
    assert safe_median([30.0, 10.0, 20.0]) == 20.0


def test_filter_outliers():
    # Empty list
    assert filter_outliers([]) == []

    # Within 40% bounds: median = 1000, bounds [600, 1400]
    normal = [1000.0, 1050.0, 950.0, 1200.0, 800.0]
    assert filter_outliers(normal) == normal

    # High outlier (>40%) and low outlier (>40%)
    # median of [1000, 1900, 2000, 2100, 3200] is 2000.
    # 40% range of 2000 is [1200, 2800].
    # 1000 is dropped (< 1200), 3200 is dropped (> 2800).
    values = [1000.0, 1900.0, 2000.0, 2100.0, 3200.0]
    filtered = filter_outliers(values)
    assert filtered == [1900.0, 2000.0, 2100.0]

    # Identical values
    assert filter_outliers([50.0, 50.0, 50.0]) == [50.0, 50.0, 50.0]


# ---- 3. Fake DB & Redis objects for get_floor ------------------------------


class FakeRedis:
    def __init__(self, data: dict[str, str] | None = None):
        self.store = dict(data or {})

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value


class FakeConnection:
    def __init__(self, rows_by_query: dict[str, dict | None] | None = None):
        self.rows_by_query = rows_by_query or {}
        self.executed_queries: list[str] = []

    async def fetchrow(self, query: str, *args):
        self.executed_queries.append(query)
        # Match query type
        if "as_of = $3" in query:
            return self.rows_by_query.get("today")
        if "as_of >= $3" in query:
            return self.rows_by_query.get("7d")
        return None


class FakePool:
    def __init__(self, conn: FakeConnection | None = None):
        self.conn = conn or FakeConnection()

    def acquire(self):
        class _Ctx:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return _Ctx(self.conn)


# ---- 4. get_floor tests ----------------------------------------------------


@pytest.mark.asyncio
async def test_get_floor_returns_none_when_empty():
    """Verify get_floor returns None when neither redis nor DB has data."""
    fake_redis = FakeRedis()
    fake_pool = FakePool(FakeConnection(rows_by_query={"today": None, "7d": None}))

    result = await get_floor(fake_pool, fake_redis, "KA-MANDYA", "ragi")
    assert result is None


@pytest.mark.asyncio
async def test_get_floor_from_redis_cache():
    """Verify 1st lookup order: redis key cached."""
    cached_data = {
        "modal_price": 3500.0,
        "afpp": 3370,
        "basis": "DISTRICT_FRESH",
        "price_date": "2026-11-12",
    }
    fake_redis = FakeRedis({"floor:KA-MANDYA:ragi": json.dumps(cached_data)})
    # Pool is None, meaning DB is not even contacted
    result = await get_floor(None, fake_redis, "KA-MANDYA", "ragi")
    assert result == cached_data


@pytest.mark.asyncio
async def test_get_floor_from_db_today():
    """Verify 2nd lookup order: price_floors row with as_of = today (IST)."""
    fake_redis = FakeRedis()
    today = today_ist()
    row = {
        "modal_price": 3600.0,
        "afpp": 3460,
        "basis": "DISTRICT_FRESH",
        "price_date": today,
    }
    fake_pool = FakePool(FakeConnection(rows_by_query={"today": row, "7d": None}))

    result = await get_floor(fake_pool, fake_redis, "KA-MANDYA", "ragi")
    assert result is not None
    assert result["modal_price"] == 3600.0
    assert result["afpp"] == 3460
    assert result["basis"] == "DISTRICT_FRESH"
    assert result["price_date"] == today.isoformat()

    # Verify cached to Redis with the expected key
    cached = await fake_redis.get("floor:KA-MANDYA:ragi")
    assert cached is not None
    assert json.loads(cached) == result


@pytest.mark.asyncio
async def test_get_floor_from_db_7d():
    """Verify 3rd lookup order: newest price_floors row within 7 days."""
    fake_redis = FakeRedis()
    past_date = today_ist() - timedelta(days=3)
    row = {
        "modal_price": 3400.0,
        "afpp": 3270,
        "basis": "DISTRICT_7D",
        "price_date": past_date,
    }
    fake_pool = FakePool(FakeConnection(rows_by_query={"today": None, "7d": row}))

    result = await get_floor(fake_pool, fake_redis, "KA-MYSURU", "maize")
    assert result is not None
    assert result["modal_price"] == 3400.0
    assert result["afpp"] == 3270
    assert result["basis"] == "DISTRICT_7D"
    assert result["price_date"] == past_date.isoformat()


@pytest.mark.asyncio
async def test_get_floor_never_raises_on_errors():
    """Verify rule 4: Never raise (log and return None) on any exception."""
    class BrokenPool:
        def acquire(self):
            raise RuntimeError("Database connection died completely")

    class BrokenRedis:
        async def get(self, key: str):
            raise ConnectionError("Redis server unreachable")

    result = await get_floor(BrokenPool(), BrokenRedis(), "KA-MANDYA", "ragi")
    assert result is None
