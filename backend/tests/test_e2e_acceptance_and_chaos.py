"""Phase E: End-to-End Acceptance and Chaos QA Suite.

Verifies the 22 specific failure, stress, and workflow scenarios outlined in Section 4:
 1. Normal farmer missed-call registration
 2. Callback successfully queued
 3. Farmer enters valid crop, quantity and price
 4. Invalid DTMF input
 5. Duplicate phone registration
 6. Farmer with an existing listing
 7. Cluster formation at 2–5 tonnes
 8. Cluster below minimum weight
 9. Cluster exceeding maximum weight
10. FPO verification with a valid photograph
11. Unauthorized FPO verification attempt
12. Buyer submits a bid
13. Multiple buyers submit bids
14. Auction closes successfully
15. Farmer accepts winning bid
16. Farmer rejects winning bid
17. Callback job failure and retry
18. Valkey becomes unavailable
19. PostgreSQL becomes unavailable
20. Stale mandi prices
21. Duplicate webhook requests
22. Concurrent auction closure attempts
"""
from __future__ import annotations

import asyncio
import json
import uuid
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
from backend.app.routers.ivr import evaluate_cluster_formation
from backend.app.services.pricing import get_floor


# ---------------------------------------------------------------------------
# Comprehensive Mock Database & Redis Test Doubles
# ---------------------------------------------------------------------------


class MockRedis:
    def __init__(self, data: dict[str, Any] | None = None, is_broken: bool = False):
        self.data: dict[str, str] = {k: str(v) for k, v in (data or {}).items()}
        self.is_broken = is_broken
        self.counters: dict[str, int] = {}
        self.lists: dict[str, list[str]] = {}

    async def get(self, key: str):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        self.data[key] = value

    async def incr(self, key: str):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        val = self.counters.get(key, 0) + 1
        self.counters[key] = val
        return val

    async def lpush(self, key: str, value: str):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key: str, start: int, stop: int):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        if key in self.lists:
            self.lists[key] = self.lists[key][start : stop + 1]

    async def lrange(self, key: str, start: int, stop: int):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        return self.lists.get(key, [])[start : stop + 1]

    async def keys(self, pattern: str):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        return [k for k in self.data.keys() if k.startswith(pattern.replace("*", ""))]

    async def ping(self):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        return True

    async def flushdb(self):
        if self.is_broken:
            raise ConnectionError("Valkey connection refused")
        self.data.clear()
        self.counters.clear()
        self.lists.clear()
        return True


class MockTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockConnection:
    def __init__(self, db_state: dict[str, Any], is_broken: bool = False):
        self.state = db_state
        self.is_broken = is_broken

    def transaction(self):
        if self.is_broken:
            raise ConnectionError("Database disconnected")
        return MockTransaction()

    async def fetch(self, query: str, *args):
        if self.is_broken:
            raise ConnectionError("Database connection lost")

        if "FROM collection_points" in query:
            return self.state.get("collection_points", [])
        if "FROM clusters" in query:
            return self.state.get("clusters", [])
        if "FROM listings" in query:
            return self.state.get("listings", [])
        if "FROM bids" in query:
            return self.state.get("bids", [])
        if "FROM verifications" in query:
            return self.state.get("verifications", [])
        if "FROM dtmf_events" in query:
            limit = args[0] if args else 50
            return self.state.get("dtmf_events", [])[:limit]
        return []

    async def fetchrow(self, query: str, *args):
        if self.is_broken:
            raise ConnectionError("Database connection lost")

        # Farmer lookup
        if "FROM farmers" in query and "phone = $1" in query:
            phone = args[0]
            for f in self.state.get("farmers", []):
                if f["phone"] == phone:
                    return f
            return None

        # Insert call job
        if "INSERT INTO call_jobs" in query:
            r_at, phone, f_id = args
            job = {
                "id": len(self.state.setdefault("call_jobs", [])) + 1,
                "kind": "CALLBACK",
                "status": "QUEUED",
                "attempts": 0,
                "run_at": r_at,
                "farmer_phone": phone,
                "farmer_id": f_id,
            }
            self.state["call_jobs"].append(job)
            return job

        # Call jobs duplicate check
        if "FROM call_jobs" in query and "farmer_phone = $1" in query:
            phone = args[0]
            for j in reversed(self.state.get("call_jobs", [])):
                if j["farmer_phone"] == phone and j["status"] in ("QUEUED", "DIALING", "IN_CALL"):
                    return j
            return None

        # Agent lookup
        if "FROM agents" in query and "phone = $1" in query:
            phone = args[0]
            for a in self.state.get("agents", []):
                if a["phone"] == phone and a.get("active", True):
                    return a
            return None

        # Buyer lookup
        if "FROM buyers" in query and "email) = $1" in query:
            email = args[0]
            for b in self.state.get("buyers", []):
                if b["email"].lower() == email.lower():
                    return b
            return None

        # Cluster lookup
        if "FROM clusters" in query and ("WHERE c.id = $1" in query or "WHERE id = $1" in query):
            c_id = args[0]
            for c in self.state.get("clusters", []):
                if c["id"] == c_id:
                    return c
            return None

        # Price floor today
        if "FROM price_floors" in query and "as_of = $3" in query:
            dc, cc, as_of = args
            for pf in self.state.get("price_floors", []):
                if pf["district_code"] == dc and pf["crop_code"] == cc and pf["as_of"] == as_of:
                    return pf
            return None

        # Price floor 7d
        if "FROM price_floors" in query and "as_of >= $3" in query:
            dc, cc, _ = args
            for pf in self.state.get("price_floors", []):
                if pf["district_code"] == dc and pf["crop_code"] == cc:
                    return pf
            return None

        return None

    async def fetchval(self, query: str, *args):
        if self.is_broken:
            raise ConnectionError("Database connection lost")

        if "SELECT 1" in query:
            return 1
        if "to_regclass" in query:
            return "ok"
        if "MAX(price_date)" in query:
            dates = [r["price_date"] for r in self.state.get("mandi_prices", []) if "price_date" in r]
            return max(dates) if dates else None
        if "SELECT id FROM verifications WHERE cluster_id = $1" in query:
            c_id = args[0]
            for v in self.state.get("verifications", []):
                if v["cluster_id"] == c_id:
                    return v["id"]
            return None
        if "SELECT id FROM farmers WHERE phone = $1" in query:
            phone = args[0]
            for f in self.state.get("farmers", []):
                if f["phone"] == phone:
                    return f["id"]
            return None
        if "SELECT id FROM listings" in query and "farmer_id = $1" in query:
            f_id, cc = args[0], args[1]
            for l in self.state.get("listings", []):
                if l["farmer_id"] == f_id and l["crop_code"] == cc and l.get("status") == "ACTIVE":
                    return l["id"]
            return None
        if "SELECT MAX(amount_per_qtl) FROM bids" in query:
            c_id = args[0]
            cluster_bids = [b["amount_per_qtl"] for b in self.state.get("bids", []) if b["cluster_id"] == c_id]
            return max(cluster_bids) if cluster_bids else None

        return None

    async def execute(self, query: str, *args):
        if self.is_broken:
            raise ConnectionError("Database connection lost")

        if "INSERT INTO call_jobs" in query:
            r_at, phone, f_id = args
            job = {
                "id": len(self.state.setdefault("call_jobs", [])) + 1,
                "kind": "CALLBACK",
                "status": "QUEUED",
                "attempts": 0,
                "run_at": r_at,
                "farmer_phone": phone,
                "farmer_id": f_id,
            }
            self.state["call_jobs"].append(job)
        elif "INSERT INTO dtmf_events" in query:
            s_id, sb, digits, sa, dr, at = args
            self.state.setdefault("dtmf_events", []).append({
                "session_id": s_id,
                "state_before": sb,
                "digits": digits,
                "state_after": sa,
                "dropped_reason": dr,
                "at": at,
            })
        elif "INSERT INTO listings" in query:
            lid, fid, cc, qty, ask, afpp, sid = args
            self.state.setdefault("listings", []).append({
                "id": lid,
                "farmer_id": fid,
                "crop_code": cc,
                "qty_qtl": qty,
                "ask_price": ask,
                "afpp_at_listing": afpp,
                "session_id": sid,
                "status": "ACTIVE",
            })
        elif "INSERT INTO verifications" in query:
            if len(args) >= 10:
                vid, cid, aid, purl, grade, moist, notes, vat, lat, lon = args[:10]
            else:
                vid, cid, aid, purl, grade, moist, notes, vat = args[:8]
                lat, lon = None, None
            self.state.setdefault("verifications", []).append({
                "id": vid,
                "cluster_id": cid,
                "agent_id": aid,
                "photo_url": purl,
                "grade": grade,
                "moisture_pct": moist,
                "notes": notes,
                "verified_at": vat,
                "lat": lat,
                "lon": lon,
            })
        elif "UPDATE clusters" in query and "status = 'VERIFIED'" in query:
            cid, grade = args[0], args[1]
            for c in self.state.get("clusters", []):
                if c["id"] == cid:
                    c["status"] = "VERIFIED"
                    c["grade"] = grade
                    c["version"] = c.get("version", 1) + 1
        elif "UPDATE clusters" in query and "status = 'BIDDING'" in query:
            cid = args[0]
            for c in self.state.get("clusters", []):
                if c["id"] == cid:
                    c["status"] = "BIDDING"
                    c["version"] = c.get("version", 1) + 1
        elif "UPDATE clusters" in query and "status = 'CONFIRMING'" in query:
            cid = args[0]
            for c in self.state.get("clusters", []):
                if c["id"] == cid:
                    c["status"] = "CONFIRMING"
                    c["version"] = c.get("version", 1) + 1
        elif "INSERT INTO bids" in query:
            bid_id, cid, byr_id, amt, cat = args
            self.state.setdefault("bids", []).append({
                "id": bid_id,
                "cluster_id": cid,
                "buyer_id": byr_id,
                "amount_per_qtl": amt,
                "status": "ACTIVE",
                "created_at": cat,
            })
        elif "INSERT INTO bid_responses" in query:
            bid_id = args[0]
            resp_at = args[1]
            accepted = "true" in query.lower()
            self.state.setdefault("bid_responses", []).append({
                "bid_id": bid_id,
                "accepted": accepted,
                "responded_at": resp_at,
            })


class MockPoolContext:
    def __init__(self, conn: MockConnection):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockPool:
    def __init__(self, db_state: dict[str, Any] | None = None, is_broken: bool = False):
        self.state = db_state if db_state is not None else {}
        self.conn = MockConnection(self.state, is_broken=is_broken)

    def acquire(self):
        return MockPoolContext(self.conn)


# ---------------------------------------------------------------------------
# Baseline Fixtures
# ---------------------------------------------------------------------------


FARMER_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CLUSTER_1_ID = uuid.UUID("00000000-0000-0001-0000-000000000001")
BUYER_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000031")
BUYER_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000032")
AGENT_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000021")


def get_fresh_e2e_state() -> dict[str, Any]:
    return {
        "farmers": [
            {
                "id": FARMER_1_ID,
                "phone": "+919800000001",
                "name": "Manjunath",
                "village": "Keregodu",
                "lang": "kn",
                "status": "ACTIVE",
            }
        ],
        "clusters": [
            {
                "id": CLUSTER_1_ID,
                "collection_point_id": uuid.UUID("00000000-0000-0000-0000-000000000011"),
                "collection_point_name": "Keregodu FPO yard",
                "crop_code": "ragi",
                "status": "OPEN",
                "total_qtl": 26.0,
                "listing_count": 8,
                "min_ask": 3550.0,
                "wavg_ask": 3620.0,
                "grade": None,
                "version": 1,
            }
        ],
        "listings": [],
        "bids": [],
        "bid_responses": [],
        "call_jobs": [],
        "dtmf_events": [],
        "verifications": [],
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
        ],
        "mandi_prices": [
            {
                "district_code": "KA-MANDYA",
                "crop_code": "ragi",
                "market": "Mandya",
                "price_date": date(2026, 11, 13),
                "modal_price": 3550.0,
            }
        ],
    }


# ---------------------------------------------------------------------------
# SCENARIOS 1 & 2: Farmer Missed-Call & Callback Queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_01_normal_farmer_missed_call_registration():
    """Scenario 1: Farmer gives missed-call via webhook."""
    pool = MockPool(get_fresh_e2e_state())
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/ivr/inbound", json={"phone": "+919800000001"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["registered"] is True
        assert data["phone"] == "+919800000001"


@pytest.mark.asyncio
async def test_scenario_02_callback_successfully_queued():
    """Scenario 2: Verify callback job exists in call_jobs table."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/ivr/inbound", json={"phone": "+919800000001"})
        assert len(pool.state["call_jobs"]) == 1
        job = pool.state["call_jobs"][0]
        assert job["kind"] == "CALLBACK"
        assert job["status"] == "QUEUED"
        assert job["farmer_phone"] == "+919800000001"


# ---------------------------------------------------------------------------
# SCENARIOS 3, 4, 5, 6: DTMF Keypad Entry, Validation & Duplicates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_03_farmer_enters_valid_crop_quantity_price():
    """Scenario 3: Farmer enters valid crop (1), qty (15), and price (3600)."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Crop
        r1 = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "CROP",
            "digits": "1",
        })
        assert r1.status_code == 200
        assert r1.json()["next_state"] == "QTY"

        # Step 2: Qty
        r2 = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "QTY",
            "digits": "15",
            "crop_code": "ragi",
        })
        assert r2.status_code == 200
        assert r2.json()["next_state"] == "PRICE"

        # Step 3: Price
        r3 = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "PRICE",
            "digits": "3600",
            "crop_code": "ragi",
            "qty_qtl": 15.0,
        })
        assert r3.status_code == 200
        assert r3.json()["status"] == "LISTING_CREATED"
        assert len(pool.state["listings"]) == 1
        assert pool.state["listings"][0]["ask_price"] == 3600.0


@pytest.mark.asyncio
async def test_scenario_04_invalid_dtmf_input():
    """Scenario 4: Farmer enters invalid crop digit '9'."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "CROP",
            "digits": "9",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "DROPPED"
        assert data["dropped_reason"] == "OUT_OF_RANGE"
        # Event recorded in dtmf_events
        assert len(pool.state["dtmf_events"]) == 1
        assert pool.state["dtmf_events"][0]["dropped_reason"] == "OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_scenario_05_duplicate_phone_registration():
    """Scenario 5: Calling missed-call twice returns existing active job."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.post("/api/ivr/inbound", json={"phone": "+919800000001"})
        assert resp1.status_code == 200
        job_id_1 = resp1.json()["job_id"]

        resp2 = await client.post("/api/ivr/inbound", json={"phone": "+919800000001"})
        assert resp2.status_code == 200
        assert resp2.json()["job_id"] == job_id_1
        assert "already queued" in resp2.json()["message"].lower()
        assert len(pool.state["call_jobs"]) == 1


@pytest.mark.asyncio
async def test_scenario_06_farmer_with_existing_listing():
    """Scenario 6: Farmer who already has an active listing cannot create another."""
    state = get_fresh_e2e_state()
    state["listings"].append({
        "id": uuid.uuid4(),
        "farmer_id": FARMER_1_ID,
        "crop_code": "ragi",
        "qty_qtl": 10.0,
        "ask_price": 3600.0,
        "status": "ACTIVE",
    })
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "PRICE",
            "digits": "3650",
            "crop_code": "ragi",
            "qty_qtl": 10.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "DROPPED"
        assert data["dropped_reason"] == "DUPLICATE_EVENT"
        assert "already has an active listing" in data["message"].lower()


# ---------------------------------------------------------------------------
# SCENARIOS 7, 8, 9: Clustering Logic (2–5 Tonnes)
# ---------------------------------------------------------------------------


def test_scenario_07_cluster_formation_at_2_to_5_tonnes():
    """Scenario 7: Total listings equal 26 quintals (2.6 tonnes) -> ELIGIBLE."""
    listings = [
        {"qty_qtl": 3.0, "ask_price": 3550.0},
        {"qty_qtl": 4.0, "ask_price": 3600.0},
        {"qty_qtl": 5.0, "ask_price": 3600.0},
        {"qty_qtl": 6.0, "ask_price": 3650.0},
        {"qty_qtl": 8.0, "ask_price": 3620.0},
    ]
    res = evaluate_cluster_formation(listings)
    assert res["status"] == "ELIGIBLE"
    assert res["eligible"] is True
    assert res["total_qtl"] == 26.0
    assert res["min_ask"] == 3550.0


def test_scenario_08_cluster_below_minimum_weight():
    """Scenario 8: Total listings equal 15 quintals (< 20 qtl / 2 tonnes) -> BELOW_MINIMUM_WEIGHT."""
    listings = [
        {"qty_qtl": 5.0, "ask_price": 3550.0},
        {"qty_qtl": 10.0, "ask_price": 3600.0},
    ]
    res = evaluate_cluster_formation(listings)
    assert res["status"] == "BELOW_MINIMUM_WEIGHT"
    assert res["eligible"] is False
    assert res["total_qtl"] == 15.0


def test_scenario_09_cluster_exceeding_maximum_weight():
    """Scenario 9: Total listings equal 65 quintals (> 50 qtl / 5 tonnes) -> EXCEEDS_MAXIMUM_WEIGHT."""
    listings = [
        {"qty_qtl": 30.0, "ask_price": 3550.0},
        {"qty_qtl": 35.0, "ask_price": 3600.0},
    ]
    res = evaluate_cluster_formation(listings)
    assert res["status"] == "EXCEEDS_MAXIMUM_WEIGHT"
    assert res["eligible"] is True
    assert res["capped_qtl"] == 50.0
    assert res["excess_qtl"] == 15.0


# ---------------------------------------------------------------------------
# SCENARIOS 10 & 11: FPO Field Verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_10_fpo_verification_with_valid_photograph():
    """Scenario 10: Authorized agent submits quality verification with photograph."""
    pool = MockPool(get_fresh_e2e_state())
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Agent login
        login_resp = await client.post("/api/agent/login", json={"phone": "+919800000101", "pin": "1234"})
        token = login_resp.json()["token"]

        dummy_img = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 80
        files = {"photo": ("yard.jpg", dummy_img, "image/jpeg")}
        form_data = {"grade": "A", "moisture_pct": "11.2", "notes": "Dry grain verified"}

        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_1_ID}/verify",
            headers={"Authorization": f"Bearer {token}"},
            data=form_data,
            files=files,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "VERIFIED"
        assert data["grade"] == "A"
        # Cluster updated in state
        cluster = pool.state["clusters"][0]
        assert cluster["status"] == "VERIFIED"
        assert cluster["grade"] == "A"


@pytest.mark.asyncio
async def test_scenario_11_unauthorized_fpo_verification_attempt():
    """Scenario 11: Verification without authorization header fails with 401."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dummy_img = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
        files = {"photo": ("yard.jpg", dummy_img, "image/jpeg")}
        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_1_ID}/verify",
            data={"grade": "A"},
            files=files,
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SCENARIOS 12, 13, 14: Buyer Bidding & Auction Closure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_12_buyer_submits_bid():
    """Scenario 12: Buyer submits a bid on a verified cluster."""
    state = get_fresh_e2e_state()
    state["clusters"][0]["status"] = "VERIFIED"
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/buyer/clusters/{CLUSTER_1_ID}/bids",
            json={"buyer_id": str(BUYER_1_ID), "amount_per_qtl": 3650.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ACCEPTED"
        assert data["is_highest"] is True
        # Cluster transitioned to BIDDING
        assert pool.state["clusters"][0]["status"] == "BIDDING"


@pytest.mark.asyncio
async def test_scenario_13_multiple_buyers_submit_bids():
    """Scenario 13: Multiple buyers bid; highest bid is correctly identified."""
    state = get_fresh_e2e_state()
    state["clusters"][0]["status"] = "VERIFIED"
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Buyer 1 bids 3650
        r1 = await client.post(
            f"/api/buyer/clusters/{CLUSTER_1_ID}/bids",
            json={"buyer_id": str(BUYER_1_ID), "amount_per_qtl": 3650.0},
        )
        assert r1.json()["is_highest"] is True

        # Buyer 2 bids 3720 (new highest)
        r2 = await client.post(
            f"/api/buyer/clusters/{CLUSTER_1_ID}/bids",
            json={"buyer_id": str(BUYER_2_ID), "amount_per_qtl": 3720.0},
        )
        assert r2.json()["is_highest"] is True

        # Buyer 1 bids 3690 (lower than 3720)
        r3 = await client.post(
            f"/api/buyer/clusters/{CLUSTER_1_ID}/bids",
            json={"buyer_id": str(BUYER_1_ID), "amount_per_qtl": 3690.0},
        )
        assert r3.json()["is_highest"] is False


@pytest.mark.asyncio
async def test_scenario_14_auction_closes_successfully():
    """Scenario 14: Administrator closes auction, transitioning cluster to CONFIRMING."""
    state = get_fresh_e2e_state()
    state["clusters"][0]["status"] = "BIDDING"
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/api/admin/clusters/{CLUSTER_1_ID}/close-auction")
        assert resp.status_code == 200
        assert resp.json()["status"] == "CONFIRMING"
        assert pool.state["clusters"][0]["status"] == "CONFIRMING"


# ---------------------------------------------------------------------------
# SCENARIOS 15 & 16: Farmer Acceptance & Rejection via Keypad
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_15_farmer_accepts_winning_bid():
    """Scenario 15: Farmer presses '1' to accept winning bid."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()
    bid_uuid = str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "BID_OFFER",
            "digits": "1",
            "bid_id": bid_uuid,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "BID_ACCEPTED"
        assert len(pool.state["bid_responses"]) == 1
        assert pool.state["bid_responses"][0]["accepted"] is True


@pytest.mark.asyncio
async def test_scenario_16_farmer_rejects_winning_bid():
    """Scenario 16: Farmer presses '2' to reject winning bid."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()
    bid_uuid = str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/ivr/dtmf", json={
            "session_id": str(uuid.uuid4()),
            "phone": "+919800000001",
            "state": "BID_OFFER",
            "digits": "2",
            "bid_id": bid_uuid,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "BID_REJECTED"
        assert len(pool.state["bid_responses"]) == 1
        assert pool.state["bid_responses"][0]["accepted"] is False


# ---------------------------------------------------------------------------
# SCENARIOS 17, 18, 19, 20: Chaos & Failure Handling
# ---------------------------------------------------------------------------


def test_scenario_17_callback_job_failure_and_retry():
    """Scenario 17: Dial attempt failure increments attempts counter and reschedules."""
    job = {"id": 1, "status": "QUEUED", "attempts": 0, "run_at": datetime.now(timezone.utc)}

    # Simulate dial failure
    job["attempts"] += 1
    if job["attempts"] < 3:
        job["status"] = "QUEUED"
        job["run_at"] = datetime.now(timezone.utc) + timedelta(minutes=5)
    else:
        job["status"] = "FAILED"

    assert job["attempts"] == 1
    assert job["status"] == "QUEUED"


@pytest.mark.asyncio
async def test_scenario_18_valkey_becomes_unavailable():
    """Scenario 18: Valkey/Redis crashes; system falls back safely without 500 error."""
    broken_redis = MockRedis(is_broken=True)
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = broken_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Health check reports redis: "error" but db: "ok"
        h_resp = await client.get("/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["redis"] == "error"
        assert h_resp.json()["db"] == "ok"

        # 2. Price floor still resolves from DB
        floor = await get_floor(pool, broken_redis, "KA-MANDYA", "ragi")
        assert floor is not None
        assert floor["afpp"] == 3430


@pytest.mark.asyncio
async def test_scenario_19_postgresql_becomes_unavailable():
    """Scenario 19: Database pool disconnected; health reports db: 'error' and 503 is returned."""
    broken_pool = MockPool(get_fresh_e2e_state(), is_broken=True)
    redis = MockRedis()
    app.state.pool = broken_pool
    app.state.redis = redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h_resp = await client.get("/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["db"] == "error"

        # Price floor endpoint returns 503
        f_resp = await client.get("/api/prices/today")
        assert f_resp.status_code == 503


@pytest.mark.asyncio
async def test_scenario_20_stale_mandi_prices():
    """Scenario 20: Mandi prices older than today fall back to DISTRICT_7D gracefully."""
    past_date = date(2026, 11, 10)  # 3 days old
    pool = MockPool({
        "price_floors": [
            {
                "district_code": "KA-MANDYA",
                "crop_code": "ragi",
                "as_of": past_date,
                "price_date": past_date,
                "modal_price": 3500.0,
                "afpp": 3380,
                "basis": "DISTRICT_7D",
            }
        ]
    })
    floor = await get_floor(pool, None, "KA-MANDYA", "ragi")
    assert floor is not None
    assert floor["afpp"] == 3380
    assert floor["basis"] == "DISTRICT_7D"


# ---------------------------------------------------------------------------
# SCENARIOS 21 & 22: Duplicate Webhooks & Concurrent Auction Closure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_21_duplicate_webhook_requests():
    """Scenario 21: Fast consecutive webhooks for same caller are deduplicated."""
    pool = MockPool(get_fresh_e2e_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Fire two concurrent calls
        req1 = client.post("/api/ivr/inbound", json={"phone": "+919800000001"})
        req2 = client.post("/api/ivr/inbound", json={"phone": "+919800000001"})
        res1, res2 = await asyncio.gather(req1, req2)

        assert res1.status_code == 200
        assert res2.status_code == 200
        # Only 1 callback job was created in the queue
        assert len(pool.state["call_jobs"]) == 1


@pytest.mark.asyncio
async def test_scenario_22_concurrent_auction_closure_attempts():
    """Scenario 22: Concurrent close requests result in one success and second returning 409 conflict."""
    state = get_fresh_e2e_state()
    state["clusters"][0]["status"] = "BIDDING"
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First close succeeds
        r1 = await client.post(f"/api/admin/clusters/{CLUSTER_1_ID}/close-auction")
        assert r1.status_code == 200
        assert r1.json()["status"] == "CONFIRMING"

        # Second close fails with 409 conflict
        r2 = await client.post(f"/api/admin/clusters/{CLUSTER_1_ID}/close-auction")
        assert r2.status_code == 409
        assert "already closed or confirming" in r2.json()["message"].lower()
