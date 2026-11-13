"""demo_reset.py rebuilds a clean demo and tells open dashboards to refetch. Real Postgres + Valkey (test database)."""
import asyncio
import time

import pytest

import demo_reset
from app import cache, db
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


async def test_reset_wipes_trade_data_and_rebuilds_the_three_demo_clusters():
    pool = await db.connect()
    await cache.connect()
    try:
        await pool.execute("INSERT INTO events (type, audience, payload) VALUES ('stale.event', 'all', '{}')")
        await cache.redis.set("sess:+910000000000", "stale")
        await cache.redis.set("rl:cb:+910000000000:day", "5")
    finally:
        await cache.close()
        await db.close()

    t0 = time.time()
    await demo_reset.main(empty=False, keep_farmers=False)
    assert time.time() - t0 < 15

    pool = await db.connect()
    await cache.connect()
    try:
        st = sorted(r["status"] for r in await pool.fetch("SELECT status FROM clusters"))
        assert st == ["BIDDING", "OPEN", "READY"]
        assert await pool.fetchval("SELECT count(*) FROM events WHERE type = 'stale.event'") == 0
        assert await pool.fetchval("SELECT count(*) FROM call_jobs") == 0
        assert await pool.fetchval("SELECT count(*) FROM farmers WHERE lang IS NOT NULL OR consent_at IS NOT NULL") == 0
        assert await pool.fetchval("SELECT count(*) FROM bids") == 0
        assert await cache.redis.get("sess:+910000000000") is None
        assert await cache.redis.get("rl:cb:+910000000000:day") is None
        assert await cache.redis.get("floor:KA-MANDYA:ragi")               # the price floor is cached again
    finally:
        await cache.close()
        await db.close()

    await demo_reset.main(empty=True, keep_farmers=False)                  # --empty: reference data only
    pool = await db.connect()
    try:
        assert await pool.fetchval("SELECT count(*) FROM clusters") == 0
        assert await pool.fetchval("SELECT count(*) FROM farmers") >= 8
    finally:
        await db.close()


def test_reset_makes_open_dashboards_refetch():
    from fastapi.testclient import TestClient
    from app.main import app
    from test_d4 import PASSWORD

    with TestClient(app) as client:
        tok = client.post("/api/auth/buyer/login", json={"email": "buyer1@demo.test", "password": PASSWORD}).json()["token"]
        with client.websocket_connect(f"/ws?token={tok}&since=999999999") as w:
            assert w.receive_json() == {"type": "resync"}                  # too far ahead after a reset: refetch
            client.portal.call(cache.redis.publish, "ad:events", "resync")  # what demo_reset.py sends at the end
            assert w.receive_json() == {"type": "resync"}
