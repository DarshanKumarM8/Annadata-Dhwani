"""D4 tests against the real Postgres + Valkey (skipped if they are not up): clustering under concurrency,
the READY transition, the outbox/WebSocket feed (timing, replay, audience filter) and the buyer REST."""
import asyncio
import json
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path

import asyncpg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dev_min_seed as seed  # noqa: E402

from app import cache, db  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import clustering  # noqa: E402
from test_reliability import STACK_UP  # noqa: E402

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")

CP = "00000000-0000-4000-8000-0000000000c9"        # private collection point: its own cluster key
PREFIX = "+9177"
PASSWORD = os.getenv("SEED_PASSWORD", "change-me")


async def setup_farmers(n: int) -> list[tuple[str, str]]:
    await seed.main(None, False)
    c = await asyncpg.connect(settings.database_url)
    await c.execute("""INSERT INTO collection_points (id,fpo_id,name,district_code,geog)
        VALUES ($1::uuid,$2::uuid,'D4 test yard','KA-MANDYA',ST_SetSRID(ST_MakePoint(76.95,12.55),4326)::geography)
        ON CONFLICT DO NOTHING""", CP, seed.FPO_ID)
    out = []
    for i in range(n):
        phone = f"{PREFIX}{i:02d}{random.randint(100_000, 999_999)}"
        fid = await c.fetchval("""INSERT INTO farmers (phone,name,fpo_id,village,district_code,geog,collection_point_id)
            VALUES ($1,'T',$2::uuid,'Testgram','KA-MANDYA',ST_SetSRID(ST_MakePoint(76.9,12.5),4326)::geography,$3::uuid)
            RETURNING id::text""", phone, seed.FPO_ID, CP)
        out.append((phone, fid))
    await c.close()
    return out


async def teardown() -> None:
    c = await asyncpg.connect(settings.database_url)
    await c.execute("DELETE FROM listings WHERE farmer_id IN (SELECT id FROM farmers WHERE phone LIKE $1)", PREFIX + "%")
    await c.execute("DELETE FROM call_sessions WHERE phone LIKE $1", PREFIX + "%")
    await c.execute("DELETE FROM clusters WHERE collection_point_id = $1::uuid", CP)
    await c.execute("DELETE FROM farmers WHERE phone LIKE $1", PREFIX + "%")
    await c.execute("DELETE FROM collection_points WHERE id = $1::uuid", CP)
    await c.close()


def session(phone, fid, qty, price=3600, crop="maize"):
    return {"id": str(uuid.uuid4()), "phone": phone, "farmer_id": fid, "kind": "LISTING", "provider": "sim",
            "call_id": "t-" + uuid.uuid4().hex[:6], "state": "DONE", "version": 1,
            "data": {"crop": crop, "qty": qty, "price": price}}


@pytest.fixture
def clean():
    asyncio.run(teardown())
    yield
    asyncio.run(teardown())


async def test_fifty_concurrent_commits_make_one_cluster_with_the_right_total(clean):
    pool = await db.connect()
    await cache.connect()
    try:
        farmers = await setup_farmers(50)
        sessions = [session(p, f, 1, 3000 + i) for i, (p, f) in enumerate(farmers)]
        codes = await asyncio.gather(*[clustering.commit_listing(pool, x) for x in sessions])
        assert len(set(codes)) == 50
        rows = await pool.fetch("SELECT * FROM clusters WHERE collection_point_id = $1::uuid", CP)
        assert len(rows) == 1
        c = rows[0]
        assert float(c["total_qtl"]) == 50 and c["listing_count"] == 50
        assert c["status"] == "READY" and float(c["min_ask"]) == 3000
        # exactly one VERIFY task for the cluster, no matter how many commits crossed 20 q
        n = await pool.fetchval("""SELECT count(*) FROM events WHERE type='task.created'
                                   AND payload->>'ref_id' = $1""", str(c["id"]))
        assert n == 1
        # idempotent: replaying a session returns the same code and adds nothing
        assert await clustering.commit_listing(pool, sessions[0]) == codes[0]
        assert await pool.fetchval("SELECT count(*) FROM listings WHERE cluster_id=$1", c["id"]) == 50
    finally:
        await cache.close()
        await db.close()


async def test_cluster_stays_open_below_20_and_turns_ready_at_20(clean):
    pool = await db.connect()
    await cache.connect()
    try:
        farmers = await setup_farmers(2)
        await clustering.commit_listing(pool, session(*farmers[0], 19))
        assert await pool.fetchval("SELECT status FROM clusters WHERE collection_point_id=$1::uuid", CP) == "OPEN"
        await clustering.commit_listing(pool, session(*farmers[1], 1))
        assert await pool.fetchval("SELECT status FROM clusters WHERE collection_point_id=$1::uuid", CP) == "READY"
    finally:
        await cache.close()
        await db.close()


def _login(client, email="buyer1@demo.test"):
    r = client.post("/api/auth/buyer/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_listing_reaches_two_dashboards_fast_and_audience_is_filtered(clean):
    from fastapi.testclient import TestClient
    from app.main import app

    farmers = asyncio.run(setup_farmers(2))

    async def max_seq():
        return await db.pool.fetchval("SELECT COALESCE(MAX(seq),0) FROM events")

    with TestClient(app) as client:
        buyer, admin = _login(client), _login(client, "admin@demo.test")
        base = client.portal.call(max_seq)
        with client.websocket_connect(f"/ws?token={buyer}&since={base}") as t1, \
                client.websocket_connect(f"/ws?token={buyer}&since={base}") as t2, \
                client.websocket_connect(f"/ws?token={admin}&since={base}") as adm:
            t0 = time.time()
            client.portal.call(clustering.commit_listing, db.pool, session(*farmers[0], 25))
            first = [(t.receive_json()["type"]) for t in (t1, t2) for _ in range(2)]
            assert time.time() - t0 < 1.0, "both dashboards must see the listing in under a second"
            assert first == ["listing.created", "cluster.updated"] * 2
            client.portal.call(clustering.commit_listing, db.pool, session(*farmers[1], 1))
            # the agent-only task.created from the first commit must never reach a buyer
            assert [t1.receive_json()["type"] for _ in range(2)] == ["listing.created", "cluster.updated"]
            admin_types = [adm.receive_json()["type"] for _ in range(5)]
            assert admin_types == ["listing.created", "cluster.updated", "task.created",
                                   "listing.created", "cluster.updated"]
        # replay: a late joiner with since=base gets the same history, in order, buyers without the task
        with client.websocket_connect(f"/ws?token={buyer}&since={base}") as late:
            msgs = [late.receive_json() for _ in range(4)]
            assert [m["type"] for m in msgs] == ["listing.created", "cluster.updated"] * 2
            assert [m["seq"] for m in msgs] == sorted(m["seq"] for m in msgs)
            # a client that has seen everything and reconnects with the last seq gets nothing old
            last = msgs[-1]["seq"]
        with client.websocket_connect(f"/ws?token={buyer}&since={last}") as caught_up:
            client.portal.call(clustering.commit_listing, db.pool, session(farmers[1][0], farmers[1][1], 1, crop="ragi"))
            assert caught_up.receive_json()["seq"] > last


def test_rest_login_lockout_auth_and_no_phone_numbers_leak(clean):
    from fastapi.testclient import TestClient
    from app.main import app

    farmers = asyncio.run(setup_farmers(1))
    with TestClient(app) as client:
        client.portal.call(clustering.commit_listing, db.pool, session(*farmers[0], 25))
        assert client.get("/api/clusters").status_code == 401
        assert client.post("/api/auth/buyer/login", json={"email": "buyer1@demo.test", "password": "nope"}
                           ).json() == {"error": "BAD_CREDENTIALS"}
        tok = _login(client)
        h = {"Authorization": f"Bearer {tok}"}
        lst = client.get("/api/clusters?status=READY,OPEN&crop=maize", headers=h).json()["clusters"]
        mine = next(c for c in lst if c["collection_point"]["name"] == "D4 test yard")
        assert mine["status"] == "READY" and mine["total_qtl"] == 25 and mine["district"] == "Mandya"
        d = client.get(f"/api/clusters/{mine['id']}", headers=h).json()
        assert d["lots"] == [{"lot_no": 1, "qty_qtl": 25.0, "ask_price": 3600.0}] and d["msp"] == 2410
        assert client.get("/api/clusters/not-a-uuid", headers=h).json() == {"error": "NOT_FOUND"}
        assert client.get("/api/clusters/" + str(uuid.uuid4()), headers=h).status_code == 404
        blob = json.dumps([lst, d])
        assert not re.search(r"\d{10}", blob) and farmers[0][0] not in blob      # no phone numbers
        # five wrong passwords lock the account
        for _ in range(5):
            client.post("/api/auth/buyer/login", json={"email": "buyer2@demo.test", "password": "bad"})
        assert client.post("/api/auth/buyer/login", json={"email": "buyer2@demo.test",
                           "password": PASSWORD}).status_code == 429
        asyncio.run(_clear_lock())


async def _clear_lock():
    import redis.asyncio as aioredis
    r = aioredis.from_url(settings.redis_url)
    await r.delete("rl:login:buyer2@demo.test")
    await r.aclose()
