"""The endpoints the agent screen (AgentApp.tsx) calls: shapes it expects, on top of the real login and verification rules."""
import io
import os
import re
import uuid

import httpx
import pytest

from app import cache, db
from app.main import app
from app.services import clustering
from test_d4 import CP, PASSWORD, session, setup_farmers
from test_d5 import teardown5
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")
PIN = os.getenv("AGENT_PIN", "1234")


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await teardown5()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield pool, http
    await teardown5()
    await cache.close()
    await db.close()


def photo():
    return {"photo": ("s.jpg", io.BytesIO(b"\xff\xd8\xff acceptance"), "image/jpeg")}


async def ready_cluster(pool, n=5):
    farmers = await setup_farmers(n)
    for i, (p, f) in enumerate(farmers):
        await clustering.commit_listing(pool, session(p, f, 5, 3000 + i))
    return str(await pool.fetchval("SELECT id FROM clusters WHERE collection_point_id = $1::uuid", CP))


async def test_agent_screen_flow_login_list_detail_verify_history(env):
    pool, http = env
    cid = await ready_cluster(pool)
    bad = await http.post("/api/agent/login", json={"phone": "+919800000099", "pin": "0000"})
    assert bad.status_code == 401 and bad.json() == {"error": "BAD_CREDENTIALS"}
    r = await http.post("/api/agent/login", json={"phone": "+919800000099", "pin": PIN})
    assert r.status_code == 200 and set(r.json()["agent"]) == {"id", "name", "fpo_id", "phone"}
    h = {"Authorization": "Bearer " + r.json()["token"]}

    cps = (await http.get("/api/agent/collection-points", headers=h)).json()
    mine = next(c for c in cps if c["name"] == "D4 test yard")
    assert set(mine) == {"id", "fpo_id", "name", "district_code"}

    lst = (await http.get(f"/api/agent/clusters?collection_point_id={mine['id']}", headers=h)).json()
    c = next(x for x in lst if x["id"] == cid)
    assert c["status"] == "READY" and c["total_qtl"] == 25 and c["collection_point_name"] == "D4 test yard"
    assert round(c["yard_lat"], 2) == 12.55 and round(c["yard_lon"], 2) == 76.95 and c["verify_radius_m"] == 500   # the screen shows the distance

    d = (await http.get(f"/api/agent/clusters/{cid}", headers=h)).json()
    assert len(d["listings"]) == 5 and d["listings"][0]["ask_price"] == 3000.0
    blob = str(d)
    assert not re.search(r"(?<![\w.])(\+?91)?[6-9]\d{9}(?![\w.])", blob)          # no full phone number
    assert all(x["farmer_phone"].startswith("+91\u2022") for x in d["listings"])    # masked

    form = {"grade": "A", "moisture_pct": "11.5", "notes": "dry", "lat": "12.55", "lon": "76.95"}
    assert (await http.post(f"/api/agent/clusters/{cid}/verify", headers=h, data={"grade": "A"}, files=photo())).json() == {"error": "LOCATION_REQUIRED"}
    far = await http.post(f"/api/agent/clusters/{cid}/verify", headers=h, data={**form, "lat": "12.9"}, files=photo())
    assert far.status_code == 422 and far.json()["error"] == "TOO_FAR" and far.json()["radius_m"] == 500 and far.json()["distance_m"] > 500
    ok = await http.post(f"/api/agent/clusters/{cid}/verify", headers=h, data=form, files=photo())
    body = ok.json()
    assert ok.status_code == 201 and body["status"] == "BIDDING" and body["grade"] == "A" and body["verification_id"]
    assert set(body) >= {"status", "verification_id", "verified_at", "cluster_id", "grade", "lat", "lon"}
    assert (await http.post(f"/api/agent/clusters/{cid}/verify", headers=h, data=form, files=photo())).json()["error"] == "ALREADY_VERIFIED"

    hist = (await http.get("/api/agent/verifications", headers=h)).json()
    assert hist[0]["cluster_id"] == cid and hist[0]["grade"] == "A" and hist[0]["photo_url"].startswith("/media/v/")
    assert hist[0]["moisture_pct"] == 11.5 and hist[0]["crop_code"] == "maize"
    assert (await http.get(f"/api/agent/clusters/{cid}", headers=h)).json()["status"] == "BIDDING"


async def test_only_an_agent_can_use_the_agent_screen_endpoints(env):
    pool, http = env
    buyer = (await http.post("/api/auth/buyer/login", json={"email": "buyer1@demo.test", "password": PASSWORD})).json()["token"]
    for path in ("/api/agent/collection-points", "/api/agent/clusters", "/api/agent/verifications", "/api/agent/me"):
        assert (await http.get(path, headers={"Authorization": "Bearer " + buyer})).status_code == 403
        assert (await http.get(path)).status_code == 401
    assert (await http.get(f"/api/agent/clusters/{uuid.uuid4()}", headers={"Authorization": "Bearer " + buyer})).status_code == 403
