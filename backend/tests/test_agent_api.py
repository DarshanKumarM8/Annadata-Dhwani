"""Unit and integration tests for Phase C: FPO Agent API."""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


# ---------------------------------------------------------------------------
# Test Mocks
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


class MockTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockConnection:
    def __init__(self, db_state: dict[str, Any]):
        self.state = db_state

    def transaction(self):
        return MockTransaction()

    async def fetch(self, query: str, *args):
        if "FROM collection_points" in query:
            return self.state.get("collection_points", [])
        if "FROM clusters c" in query and "WHERE cp.fpo_id" in query:
            return self.state.get("clusters", [])
        if "FROM listings l" in query:
            c_id = args[0]
            return [
                l for l in self.state.get("listings", [])
                if l["cluster_id"] == c_id
            ]
        if "FROM verifications v" in query:
            return self.state.get("verifications", [])
        return []

    async def fetchrow(self, query: str, *args):
        if "FROM agents" in query:
            phone = args[0]
            for a in self.state.get("agents", []):
                if a["phone"] == phone and a.get("active", True):
                    return a
            return None
        if "FROM clusters" in query and ("WHERE c.id = $1" in query or "WHERE id = $1" in query):
            c_id = args[0]
            for c in self.state.get("clusters", []):
                if c["id"] == c_id:
                    return c
            return None
        return None

    async def fetchval(self, query: str, *args):
        if "SELECT id FROM verifications WHERE cluster_id = $1" in query:
            c_id = args[0]
            for v in self.state.get("verifications", []):
                if v["cluster_id"] == c_id:
                    return v["id"]
            return None
        return None

    async def execute(self, query: str, *args):
        if "INSERT INTO verifications" in query:
            # Expect args: v_id, c_id, a_id, p_url, grade, moist, notes, v_at, lat, lon
            if len(args) == 10:
                v_id, c_id, a_id, p_url, grade, moist, notes, v_at, lat, lon = args
            else:
                # fallback for older calls without lat/lon
                v_id, c_id, a_id, p_url, grade, moist, notes, v_at = args[:8]
                lat, lon = None, None
            self.state.setdefault("verifications", []).append({
                "id": v_id,
                "cluster_id": c_id,
                "agent_id": a_id,
                "photo_url": p_url,
                "grade": grade,
                "moisture_pct": moist,
                "notes": notes,
                "verified_at": v_at,
                "crop_code": "ragi",
                "total_qtl": 17.0,
                "lat": lat,
                "lon": lon,
            })
        elif "UPDATE clusters" in query and "SET status = 'VERIFIED'" in query:
            c_id = args[0]
            grade = args[1]
            for c in self.state.get("clusters", []):
                if c["id"] == c_id:
                    c["status"] = "VERIFIED"
                    c["grade"] = grade
                    c["version"] = c.get("version", 1) + 1


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
# Setup Fixture Data
# ---------------------------------------------------------------------------


AGENT_UUID = uuid.UUID("00000000-0000-0000-0000-000000000021")
FPO_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CP_UUID = uuid.UUID("00000000-0000-0000-0000-000000000011")
CLUSTER_UUID = uuid.UUID("00000000-0000-0001-0000-000000000001")


def get_default_db_state():
    return {
        "agents": [
            {
                "id": AGENT_UUID,
                "fpo_id": FPO_UUID,
                "name": "Kavya",
                "phone": "+919800000101",
                "pin_hash": "1234",
                "active": True,
            }
        ],
        "collection_points": [
            {
                "id": CP_UUID,
                "fpo_id": FPO_UUID,
                "name": "Keregodu FPO yard",
                "district_code": "KA-MANDYA",
            }
        ],
        "clusters": [
            {
                "id": CLUSTER_UUID,
                "collection_point_id": CP_UUID,
                "collection_point_name": "Keregodu FPO yard",
                "crop_code": "ragi",
                "status": "OPEN",
                "total_qtl": 17.0,
                "listing_count": 6,
                "min_ask": 3550.0,
                "wavg_ask": 3625.0,
                "grade": None,
                "version": 1,
            }
        ],
        "listings": [
            {
                "id": uuid.uuid4(),
                "cluster_id": CLUSTER_UUID,
                "farmer_name": "Manjunath",
                "farmer_phone": "+919800000005",
                "village": "Keregodu",
                "qty_qtl": 3.0,
                "ask_price": 3550.0,
            }
        ],
        "verifications": [],
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_login_success():
    pool = MockPool(get_default_db_state())
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["token"].startswith("agt_")
        assert data["agent"]["name"] == "Kavya"
        assert data["agent"]["phone"] == "+919800000101"


@pytest.mark.asyncio
async def test_agent_login_wrong_pin():
    pool = MockPool(get_default_db_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "9999"},
        )
        assert resp.status_code == 401
        assert "incorrect pin" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_agent_login_unknown_phone():
    pool = MockPool(get_default_db_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919999999999", "pin": "1234"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_unauthorized_access():
    app.state.pool = MockPool(get_default_db_state())
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # No header
        resp = await client.get("/api/agent/clusters")
        assert resp.status_code == 401

        # Bad header
        resp = await client.get(
            "/api/agent/clusters",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_get_clusters_and_detail():
    pool = MockPool(get_default_db_state())
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Login
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get clusters
        clusters_resp = await client.get("/api/agent/clusters", headers=headers)
        assert clusters_resp.status_code == 200
        clusters = clusters_resp.json()
        assert len(clusters) == 1
        assert clusters[0]["crop_code"] == "ragi"
        assert clusters[0]["status"] == "OPEN"

        # 3. Get cluster detail
        detail_resp = await client.get(
            f"/api/agent/clusters/{CLUSTER_UUID}", headers=headers
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == str(CLUSTER_UUID)
        assert len(detail["listings"]) == 1
        assert detail["listings"][0]["farmer_name"] == "Manjunath"


@pytest.mark.asyncio
async def test_agent_verify_cluster_success():
    pool = MockPool(get_default_db_state())
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create dummy image bytes
        dummy_img = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100

        files = {
            "photo": ("test_produce.jpg", dummy_img, "image/jpeg"),
        }
        form_data = {
            "grade": "A",
            "moisture_pct": "11.5",
            "notes": "Produce inspected in yard. Good dry grain.",
        }

        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_UUID}/verify",
            headers=headers,
            data=form_data,
            files=files,
        )
        assert resp.status_code == 200
        res = resp.json()
        assert res["status"] == "VERIFIED"
        assert res["grade"] == "A"
        assert "verification_id" in res

        # Verify cluster in DB was updated to VERIFIED
        cluster = next(c for c in pool.state["clusters"] if c["id"] == CLUSTER_UUID)
        assert cluster["status"] == "VERIFIED"
        assert cluster["grade"] == "A"


@pytest.mark.asyncio
async def test_agent_verify_cluster_duplicate_conflict():
    state = get_default_db_state()
    # Mark cluster as already verified
    state["clusters"][0]["status"] = "VERIFIED"
    state["verifications"].append({
        "id": uuid.uuid4(),
        "cluster_id": CLUSTER_UUID,
        "agent_id": AGENT_UUID,
        "photo_url": "/uploads/test.jpg",
        "grade": "B",
        "moisture_pct": 12.0,
        "notes": "Done",
        "verified_at": datetime.now(timezone.utc),
    })

    pool = MockPool(state)
    redis = MockRedis()
    app.state.pool = pool
    app.state.redis = redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        dummy_img = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
        files = {"photo": ("test.jpg", dummy_img, "image/jpeg")}
        form_data = {"grade": "A"}

        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_UUID}/verify",
            headers=headers,
            data=form_data,
            files=files,
        )
        assert resp.status_code == 409
        assert "already been verified" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_agent_verify_unsupported_media_type():
    pool = MockPool(get_default_db_state())
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt to upload a text file
        files = {"photo": ("malicious.txt", b"plain text payload", "text/plain")}
        form_data = {"grade": "A"}

        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_UUID}/verify",
            headers=headers,
            data=form_data,
            files=files,
        )
        assert resp.status_code == 415
        assert "unsupported image type" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_agent_get_verifications_history():
    state = get_default_db_state()
    now_utc = datetime.now(timezone.utc)
    state["verifications"].append({
        "id": uuid.uuid4(),
        "cluster_id": CLUSTER_UUID,
        "agent_id": AGENT_UUID,
        "photo_url": "/uploads/verifications/sample.jpg",
        "grade": "A",
        "moisture_pct": 11.2,
        "notes": "Batch verified",
        "verified_at": now_utc,
        "crop_code": "ragi",
        "total_qtl": 17.0,
    })

    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/agent/verifications", headers=headers)
        assert resp.status_code == 200
        history = resp.json()
        assert len(history) == 1
        assert history[0]["grade"] == "A"
        assert history[0]["crop_code"] == "ragi"
        assert history[0]["photo_url"] == "/uploads/verifications/sample.jpg"


@pytest.mark.asyncio
async def test_agent_verify_cluster_with_geotag():
    state = get_default_db_state()
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        dummy_jpeg = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
            + b"\x00" * 64
        )
        files = {"photo": ("yard.jpg", dummy_jpeg, "image/jpeg")}
        form_data = {
            "grade": "B",
            "moisture_pct": "12.0",
            "notes": "Verified at yard",
            "lat": "12.6300",
            "lon": "76.9200",
        }

        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_UUID}/verify",
            headers=headers,
            data=form_data,
            files=files,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "VERIFIED"
        assert data["lat"] == 12.6300
        assert data["lon"] == 76.9200
        assert state["verifications"][0]["lat"] == 12.6300
        assert state["verifications"][0]["lon"] == 76.9200


@pytest.mark.asyncio
async def test_agent_verify_cluster_partial_geotag_rejected():
    state = get_default_db_state()
    pool = MockPool(state)
    app.state.pool = pool
    app.state.redis = MockRedis()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_resp = await client.post(
            "/api/agent/login",
            json={"phone": "+919800000101", "pin": "1234"},
        )
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        dummy_jpeg = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
            + b"\x00" * 64
        )
        files = {"photo": ("yard.jpg", dummy_jpeg, "image/jpeg")}
        # lat only
        form_data = {"grade": "B", "lat": "12.6300"}

        resp = await client.post(
            f"/api/agent/clusters/{CLUSTER_UUID}/verify",
            headers=headers,
            data=form_data,
            files=files,
        )
        assert resp.status_code == 400
        assert "both latitude and longitude must be provided" in resp.json()["message"].lower()
