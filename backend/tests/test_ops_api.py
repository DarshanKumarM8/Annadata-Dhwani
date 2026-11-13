"""Async integration and unit tests for FastAPI Operations & IVR endpoints.

Tests:
- GET /health
- GET /api/ops/calls
- GET /api/ops/dtmf
- POST /api/ops/chaos/flush-redis
- POST /api/admin/clusters/{id}/close-auction
- POST /api/ivr/inbound
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


# ---------------------------------------------------------------------------
# Fake Database & Redis Mocks
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self, data: dict[str, Any] | None = None):
        self.store = dict(data or {})

    async def ping(self):
        return True

    async def flushdb(self):
        self.store.clear()
        return True

    async def get(self, key: str):
        val = self.store.get(key)
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return val

    async def set(self, key: str, value: Any, ex: int | None = None):
        self.store[key] = value

    async def keys(self, pattern: str):
        # simple prefix match
        prefix = pattern.replace("*", "")
        return [k for k in self.store.keys() if k.startswith(prefix)]

    async def lrange(self, key: str, start: int, stop: int):
        lst = self.store.get(key, [])
        if isinstance(lst, list):
            return lst[start : stop + 1]
        return []

    async def incr(self, key: str):
        cur = int(self.store.get(key, 0)) + 1
        self.store[key] = cur
        return cur

    async def aclose(self):
        pass


class FakeConnection:
    def __init__(self, cluster_exists: bool = True):
        self.cluster_exists = cluster_exists
        self.inserted_jobs = []

    async def fetchval(self, query: str, *args):
        if "SELECT 1" in query:
            return 1
        if "MAX(price_date)" in query:
            return date.today()
        if "to_regclass" in query:
            return True
        if "count(*) FROM call_jobs" in query:
            return 14
        return None

    async def fetchrow(self, query: str, *args):
        if "FROM farmers WHERE phone" in query:
            return {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "name": "Ningappa",
                "lang": "kn",
                "consent_version": "v1",
                "status": "ACTIVE",
            }
        if "FROM clusters WHERE id" in query:
            if self.cluster_exists:
                return {
                    "id": args[0],
                    "status": "BIDDING",
                }
            return None
        if "INSERT INTO call_jobs" in query:
            job_id = len(self.inserted_jobs) + 1
            self.inserted_jobs.append(job_id)
            return {"id": job_id, "status": "QUEUED"}
        return None

    async def fetch(self, query: str, *args):
        if "FROM call_sessions" in query:
            return [
                {
                    "phone": "+919845012345",
                    "phone_masked": "+91•••••2345",
                    "kind": "LISTING",
                    "state": "PRICE",
                    "provider": "sim",
                    "version": 7,
                    "updated_at": datetime.now(timezone.utc),
                }
            ]
        if "FROM call_jobs" in query:
            return [
                {
                    "id": 101,
                    "kind": "CALLBACK",
                    "status": "QUEUED",
                    "attempts": 1,
                    "run_at": datetime.now(timezone.utc),
                }
            ]
        if "FROM dtmf_events" in query:
            return [
                {
                    "session_id": "sess-1",
                    "state_before": "QTY",
                    "digits": "3",
                    "state_after": "QTY_CONFIRM",
                    "dropped_reason": None,
                    "at": datetime.now(timezone.utc),
                },
                {
                    "session_id": "sess-2",
                    "state_before": "PRICE",
                    "digits": "9",
                    "state_after": "PRICE",
                    "dropped_reason": "BOUNCE",
                    "at": datetime.now(timezone.utc),
                },
            ]
        return []

    async def execute(self, query: str, *args):
        pass

    def transaction(self):
        class _Tx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return _Tx()


class FakePool:
    def __init__(self, cluster_exists: bool = True):
        self.conn = FakeConnection(cluster_exists=cluster_exists)

    def acquire(self):
        class _Ctx:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                pass

        return _Ctx(self.conn)

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    # Inject fake dependencies into app.state
    app.state.pool = FakePool(cluster_exists=True)
    app.state.redis = FakeRedis(
        {
            "session:test": {
                "phone_masked": "+91•••••9999",
                "kind": "LISTING",
                "state": "PRICE",
                "provider": "sim",
                "version": 3,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Verify GET /health returns expected fields and 200 OK."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["db"] == "ok"
    assert data["redis"] == "ok"
    assert isinstance(data["tts_clips"], int)
    assert data["tts_clips"] >= 0
    assert isinstance(data["price_age_days"], int)
    assert data["price_age_days"] >= 0
    assert isinstance(data["provider"], str)
    assert isinstance(data["public_base_url_ok"], bool)


@pytest.mark.asyncio
async def test_ops_calls_endpoint(client: AsyncClient):
    """Verify GET /api/ops/calls returns sessions, jobs, and breaker gauge."""
    resp = await client.get("/api/ops/calls")
    assert resp.status_code == 200
    data = resp.json()

    assert "sessions" in data
    assert "jobs" in data
    assert "breaker" in data

    # Breaker verification
    breaker = data["breaker"]
    assert "calls_today" in breaker
    assert "budget" in breaker
    assert breaker["budget"] > 0

    # Sessions format verification
    assert isinstance(data["sessions"], list)
    if data["sessions"]:
        s = data["sessions"][0]
        assert "phone_masked" in s
        assert "kind" in s
        assert "state" in s
        assert "provider" in s
        assert "version" in s
        assert "updated_at" in s


@pytest.mark.asyncio
async def test_ops_dtmf_endpoint(client: AsyncClient):
    """Verify GET /api/ops/dtmf returns events list with dropped_reason."""
    resp = await client.get("/api/ops/dtmf?limit=10")
    assert resp.status_code == 200
    data = resp.json()

    assert "events" in data
    assert isinstance(data["events"], list)
    assert len(data["events"]) > 0

    ev = data["events"][0]
    assert "session_id" in ev
    assert "state_before" in ev
    assert "digits" in ev
    assert "state_after" in ev
    assert "dropped_reason" in ev
    assert "at" in ev


@pytest.mark.asyncio
async def test_chaos_flush_redis(client: AsyncClient):
    """Verify POST /api/ops/chaos/flush-redis flushes the cache."""
    resp = await client.post("/api/ops/chaos/flush-redis")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_chaos_flush_redis_when_unavailable(client: AsyncClient):
    """Verify POST /api/ops/chaos/flush-redis returns 503 if redis is None."""
    app.state.redis = None
    resp = await client.post("/api/ops/chaos/flush-redis")
    assert resp.status_code == 503
    assert resp.json()["error"] == "REDIS_UNAVAILABLE"


@pytest.mark.asyncio
async def test_close_auction_success(client: AsyncClient):
    """Verify POST /api/admin/clusters/{id}/close-auction succeeds with CONFIRMING."""
    cluster_id = "00000000-0000-0000-0001-000000000001"
    resp = await client.post(f"/api/admin/clusters/{cluster_id}/close-auction")
    assert resp.status_code == 200
    assert resp.json() == {"status": "CONFIRMING"}


@pytest.mark.asyncio
async def test_close_auction_invalid_uuid(client: AsyncClient):
    """Verify POST /api/admin/clusters/{id}/close-auction returns 404 on malformed UUID."""
    resp = await client.post("/api/admin/clusters/not-a-uuid/close-auction")
    assert resp.status_code == 404
    assert resp.json()["error"] == "CLUSTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_close_auction_not_found(client: AsyncClient):
    """Verify POST /api/admin/clusters/{id}/close-auction returns 404 when cluster missing."""
    app.state.pool = FakePool(cluster_exists=False)
    missing_id = "00000000-0000-0000-0001-999999999999"
    resp = await client.post(f"/api/admin/clusters/{missing_id}/close-auction")
    assert resp.status_code == 404
    assert resp.json()["error"] == "CLUSTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_inbound_missed_call_success_json(client: AsyncClient):
    """Verify POST /api/ivr/inbound queues callback job from JSON payload."""
    resp = await client.post(
        "/api/ivr/inbound",
        json={"phone": "+919845012345"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "QUEUED"
    assert data["phone"] == "+919845012345"
    assert "job_id" in data


@pytest.mark.asyncio
async def test_inbound_missed_call_success_form(client: AsyncClient):
    """Verify POST /api/ivr/inbound handles telephony provider form data (From=+91...)."""
    resp = await client.post(
        "/api/ivr/inbound",
        data={"From": "+919800000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "QUEUED"
    assert data["phone"] == "+919800000001"
    assert data["registered"] is True


@pytest.mark.asyncio
async def test_inbound_missed_call_invalid_phone(client: AsyncClient):
    """Verify POST /api/ivr/inbound rejects non-E.164 phone with 422."""
    resp = await client.post(
        "/api/ivr/inbound",
        json={"phone": "invalid-phone-number"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_PHONE"
