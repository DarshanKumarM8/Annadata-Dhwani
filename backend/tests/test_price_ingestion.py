"""Unit and API integration tests for Phase B: Mandi price ingestion & pricing logic."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure backend/app/services is on sys.path
_services = str(Path(__file__).resolve().parent.parent / "app" / "services")
if _services not in sys.path:
    sys.path.insert(0, _services)

from backend.app.main import app
from backend.scripts.ingest_prices import (
    _parse_date,
    _safe_float,
    ingest_prices,
)


# ---------------------------------------------------------------------------
# Mock Database & Redis Test Fakes
# ---------------------------------------------------------------------------


class MockRedis:
    def __init__(self):
        self.data: dict[str, str] = {}

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value

    async def ping(self):
        return True


class MockConnection:
    def __init__(self, db_state: dict[str, Any]):
        self.state = db_state

    async def fetch(self, query: str, *args):
        # Districts
        if "FROM districts" in query:
            return [
                {
                    "code": "KA-MANDYA",
                    "name": "Mandya",
                    "agmark_state": "Karnataka",
                    "agmark_district": "Mandya",
                },
                {
                    "code": "KA-MYSURU",
                    "name": "Mysuru",
                    "agmark_state": "Karnataka",
                    "agmark_district": "Mysore",
                },
            ]
        # Crops
        if "FROM crops" in query:
            return [
                {"code": "ragi", "agmark_name": "Ragi (Finger Millet)"},
                {"code": "paddy_common", "agmark_name": "Paddy(Dhan)(Common)"},
            ]
        # Deduction rules
        if "FROM deduction_rules" in query:
            return [
                {
                    "district_code": "KA-MANDYA",
                    "transport_per_qtl": 50,
                    "handling_per_qtl": 10,
                    "pct_deduction": 0.02,
                },
                {
                    "district_code": "KA-MYSURU",
                    "transport_per_qtl": 50,
                    "handling_per_qtl": 10,
                    "pct_deduction": 0.02,
                },
            ]
        # mandi_prices stored rows
        if "FROM mandi_prices" in query and "ORDER BY price_date DESC" in query:
            district_code = args[0] if args else "KA-MANDYA"
            crop_code = args[1] if len(args) > 1 else "ragi"
            # Return last 7 days of stored records
            records = [
                r for r in self.state.get("mandi_prices", [])
                if r["district_code"] == district_code and r["crop_code"] == crop_code
            ]
            records.sort(key=lambda x: x["price_date"], reverse=True)
            return records
        # price_floors
        if "FROM price_floors" in query:
            return self.state.get("price_floors", [])

        return []

    async def fetchrow(self, query: str, *args):
        if "FROM price_floors" in query:
            district_code = args[0]
            crop_code = args[1]
            for r in self.state.get("price_floors", []):
                if r["district_code"] == district_code and r["crop_code"] == crop_code:
                    return r
            return None
        return None

    async def fetchval(self, query: str, *args):
        if "SELECT 1" in query:
            return 1
        if "MAX(price_date)" in query:
            dates = [r["price_date"] for r in self.state.get("mandi_prices", [])]
            return max(dates) if dates else None
        return None

    async def execute(self, query: str, *args):
        if "INSERT INTO mandi_prices" in query:
            # Upsert into in-memory state
            dc, cc, market, p_date, min_p, max_p, modal_p, src, _ = args
            existing = None
            for r in self.state.setdefault("mandi_prices", []):
                if (
                    r["district_code"] == dc
                    and r["crop_code"] == cc
                    and r["market"] == market
                    and r["price_date"] == p_date
                ):
                    existing = r
                    break
            if existing:
                existing["min_price"] = min_p
                existing["max_price"] = max_p
                existing["modal_price"] = modal_p
            else:
                self.state["mandi_prices"].append({
                    "district_code": dc,
                    "crop_code": cc,
                    "market": market,
                    "price_date": p_date,
                    "min_price": min_p,
                    "max_price": max_p,
                    "modal_price": modal_p,
                    "source": src,
                })
        elif "INSERT INTO price_floors" in query:
            dc, cc, as_of, p_date, modal_p, afpp, basis = args
            existing = None
            for r in self.state.setdefault("price_floors", []):
                if r["district_code"] == dc and r["crop_code"] == cc and r["as_of"] == as_of:
                    existing = r
                    break
            if existing:
                existing["price_date"] = p_date
                existing["modal_price"] = modal_p
                existing["afpp"] = afpp
                existing["basis"] = basis
            else:
                self.state["price_floors"].append({
                    "district_code": dc,
                    "crop_code": cc,
                    "as_of": as_of,
                    "price_date": p_date,
                    "modal_price": modal_p,
                    "afpp": afpp,
                    "basis": basis,
                })


class MockPoolContext:
    def __init__(self, conn: MockConnection):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockPool:
    def __init__(self, db_state: dict[str, Any] | None = None):
        self.state = db_state if db_state is not None else {}
        self.conn = MockConnection(self.state)

    def acquire(self):
        return MockPoolContext(self.conn)


# ---------------------------------------------------------------------------
# Tests: Normalization and Ingestion Helpers
# ---------------------------------------------------------------------------


def test_parse_date_formats():
    assert _parse_date("13/11/2026") == date(2026, 11, 13)
    assert _parse_date("2026-11-13") == date(2026, 11, 13)
    assert _parse_date("  01/01/2025  ") == date(2025, 1, 1)


def test_safe_float():
    assert _safe_float("3550") == 3550.0
    assert _safe_float("3550.75") == 3550.75
    assert _safe_float(2200) == 2200.0
    assert _safe_float("") is None
    assert _safe_float("invalid") is None
    assert _safe_float(None) is None


# ---------------------------------------------------------------------------
# Tests: Ingestion from Fixtures Pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_prices_from_fixtures_duplicate_safe():
    """Verify full ingestion flow from fixture files, duplicate prevention, and floor calc."""
    fixtures_dir = "contracts/fixtures"
    pool = MockPool()
    redis = MockRedis()

    # Run ingestion first time
    results = await ingest_prices(
        pool=pool,
        rds=redis,
        fixtures_dir=fixtures_dir,
    )
    assert len(results) > 0
    # Every district-crop pair has a result
    ragi_mandya = next(
        r for r in results if r["district_code"] == "KA-MANDYA" and r["crop_code"] == "ragi"
    )
    assert ragi_mandya["basis"] in ("DISTRICT_FRESH", "DISTRICT_7D")
    assert ragi_mandya["afpp"] is not None
    assert ragi_mandya["modal_price"] is not None

    # Redis cached correctly
    cached = await redis.get("floor:KA-MANDYA:ragi")
    assert cached is not None
    cached_obj = json.loads(cached)
    assert cached_obj["afpp"] == ragi_mandya["afpp"]

    # Verify duplicate prevention: run a second time
    count_before = len(pool.state.get("mandi_prices", []))
    await ingest_prices(pool=pool, rds=redis, fixtures_dir=fixtures_dir)
    count_after = len(pool.state.get("mandi_prices", []))
    assert count_before == count_after, "Duplicate records were inserted on second ingestion run"


# ---------------------------------------------------------------------------
# Tests: API Endpoints (Floor, History, Ingest)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_get_floor_success():
    pool = MockPool({
        "price_floors": [
            {
                "district_code": "KA-MANDYA",
                "crop_code": "ragi",
                "as_of": date(2026, 11, 13),
                "price_date": date(2026, 11, 13),
                "modal_price": 3550.0,
                "afpp": 3430,
                "basis": "DISTRICT_FRESH",
            }
        ]
    })
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/prices/floor?district_code=KA-MANDYA&crop_code=ragi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["district_code"] == "KA-MANDYA"
        assert data["crop_code"] == "ragi"
        assert data["afpp"] == 3430
        assert data["basis"] == "DISTRICT_FRESH"


@pytest.mark.asyncio
async def test_api_get_floor_not_found():
    pool = MockPool({"price_floors": []})
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/prices/floor?district_code=NONEXISTENT&crop_code=unknown")
        assert resp.status_code == 404
        assert "not found" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_api_get_today_floors():
    today = date(2026, 11, 13)
    pool = MockPool({
        "price_floors": [
            {
                "district_code": "KA-MANDYA",
                "crop_code": "ragi",
                "as_of": today,
                "price_date": today,
                "modal_price": 3550.0,
                "afpp": 3430,
                "basis": "DISTRICT_FRESH",
            },
            {
                "district_code": "KA-MANDYA",
                "crop_code": "paddy_common",
                "as_of": today,
                "price_date": today,
                "modal_price": 2200.0,
                "afpp": 2080,
                "basis": "DISTRICT_FRESH",
            },
        ]
    })
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/prices/today")
        assert resp.status_code == 200
        floors = resp.json()
        assert len(floors) == 2
        crops = {f["crop_code"] for f in floors}
        assert "ragi" in crops
        assert "paddy_common" in crops


@pytest.mark.asyncio
async def test_api_get_price_history():
    today = date(2026, 11, 13)
    pool = MockPool({
        "mandi_prices": [
            {
                "district_code": "KA-MANDYA",
                "crop_code": "ragi",
                "market": "Mandya",
                "price_date": today,
                "min_price": 3450.0,
                "max_price": 3700.0,
                "modal_price": 3550.0,
                "source": "data.gov.in",
            },
            {
                "district_code": "KA-MANDYA",
                "crop_code": "ragi",
                "market": "Mandya",
                "price_date": today - timedelta(days=1),
                "min_price": 3400.0,
                "max_price": 3680.0,
                "modal_price": 3540.0,
                "source": "data.gov.in",
            },
        ]
    })
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/prices/history?district_code=KA-MANDYA&crop_code=ragi&days=7")
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 2
        assert history[0]["market"] == "Mandya"
        assert history[0]["modal_price"] == 3550.0


@pytest.mark.asyncio
async def test_api_trigger_ingest_prices():
    pool = MockPool()
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/ops/ingest-prices",
            json={"from_fixtures": "contracts/fixtures"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["results"]) > 0
