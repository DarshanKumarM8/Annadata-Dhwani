"""Buyer-dashboard data: the reference-price box is never empty when the database has mandi prices, and a verification's photo
and grade reach the cluster data (list, detail and the live event) as a real, reachable image. Test database."""
import io
import re
from pathlib import Path

import httpx
import pytest

import demo_reset
from app import cache, db
from app.config import settings
from app.main import app
from app.services import clustering, pricing, views
from test_d4 import CP, PASSWORD, session, setup_farmers
from test_d5 import teardown5
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")
SAMPLE = (Path(__file__).resolve().parents[1] / "app" / "static" / "sample_grain.jpg").read_bytes()


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await teardown5()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
        tok = (await http.post("/api/auth/buyer/login", json={"email": "buyer1@demo.test", "password": PASSWORD})).json()["token"]
        yield pool, http, {"Authorization": "Bearer " + tok}
    for q in ("DELETE FROM price_floors", "DELETE FROM mandi_prices"):
        await pool.execute(q)
    for k in await cache.redis.keys("floor:*"):
        await cache.redis.delete(k)
    await teardown5()
    await cache.close()
    await db.close()


async def clusters_of_every_crop(pool):
    farmers = await setup_farmers(3)
    for (p, f), crop in zip(farmers, ("ragi", "maize", "paddy_common")):
        await clustering.commit_listing(pool, session(p, f, 25, 3000, crop=crop))
    return {r["crop_code"]: str(r["id"]) for r in await pool.fetch(
        "SELECT id, crop_code FROM clusters WHERE collection_point_id = $1::uuid", CP)}


async def detail(http, h, cid):
    r = await http.get(f"/api/clusters/{cid}", headers=h)
    assert r.status_code == 200
    return r.json()


async def test_every_cluster_has_a_reference_price_and_it_survives_a_redis_flush(env):
    pool, http, h = env
    ids = await clusters_of_every_crop(pool)
    assert await pricing.refresh(pool, cache.redis) == 3                     # the saved Agmarknet samples: one floor per crop
    for crop, cid in ids.items():
        d = await detail(http, h, cid)
        ref = d["price_ref"]
        assert ref and ref["modal_price"] > ref["afpp"] > 0 and ref["basis"] and ref["price_date"], crop
        assert d["msp"] and d["msp"] > 0, crop
    await cache.redis.flushdb()                                              # Redis gone: the stored floor still answers
    cache.load_scripts()
    assert all([(await detail(http, h, cid))["price_ref"] for cid in ids.values()])


async def test_the_price_is_computed_on_the_spot_when_no_floor_is_stored(env):
    pool, http, h = env
    ids = await clusters_of_every_crop(pool)
    await pricing.refresh(pool, cache.redis)
    await pool.execute("DELETE FROM price_floors")                           # no stored floor, but mandi prices exist
    await cache.redis.flushdb()
    ref = (await detail(http, h, ids["maize"]))["price_ref"]
    assert ref and ref["afpp"] > 0 and ref["modal_price"] > ref["afpp"]
    assert ref["afpp"] % 10 == 0 and ref["basis"] in ("DISTRICT_FRESH", "DISTRICT_7D", "STALE")


async def test_with_no_mandi_price_at_all_the_reference_is_empty_but_msp_still_shows(env):
    pool, http, h = env
    ids = await clusters_of_every_crop(pool)
    for q in ("DELETE FROM price_floors", "DELETE FROM mandi_prices"):
        await pool.execute(q)
    await cache.redis.flushdb()
    d = await detail(http, h, ids["ragi"])
    assert d["price_ref"] is None and d["msp"] == 5205.0                     # honest: no invented price; MSP is the screen's fallback


async def test_a_verification_photo_and_grade_reach_the_list_the_detail_and_the_live_event(env):
    pool, http, h = env
    ids = await clusters_of_every_crop(pool)
    cid = ids["ragi"]
    before = await detail(http, h, cid)
    assert before["grade"] is None and before["photo_url"] is None
    agent = (await http.post("/api/auth/agent/login", json={"phone": "+919800000099", "pin": "1234"})).json()["token"]
    ah = {"Authorization": "Bearer " + agent}
    yard = await pool.fetchrow("SELECT ST_Y(geog::geometry) AS lat, ST_X(geog::geometry) AS lon FROM collection_points WHERE id = $1::uuid", CP)
    form = {"grade": "A", "lat": str(yard["lat"]), "lon": str(yard["lon"]), "accuracy_m": "10",
            "captured_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
    bad = await http.post(f"/api/agent/clusters/{cid}/verification", headers=ah, data=form,
                          files={"photo": ("x.jpg", io.BytesIO(b"<html><script>alert(1)</script></html>"), "image/jpeg")})
    assert bad.status_code == 422 and bad.json()["error"] == "BAD_PHOTO"      # a web page is not a photo
    assert (await detail(http, h, cid))["status"] == "READY"                  # and nothing changed
    ok = await http.post(f"/api/agent/clusters/{cid}/verification", headers=ah, data=form,
                         files={"photo": ("s.jpg", io.BytesIO(SAMPLE), "image/jpeg")})
    assert ok.status_code == 201

    d = await detail(http, h, cid)
    assert d["grade"] == "A" and d["status"] == "BIDDING" and d["version"] > before["version"]
    assert re.fullmatch(r"/media/v/[0-9a-f]{32}\.jpg", d["photo_url"])
    lst = (await http.get("/api/clusters", headers=h)).json()["clusters"]
    assert next(c for c in lst if c["id"] == cid)["photo_url"] == d["photo_url"]
    ev = await pool.fetchval("SELECT payload FROM events WHERE type = 'cluster.updated' AND payload->>'id' = $1 ORDER BY seq DESC LIMIT 1", cid)
    ev = ev if isinstance(ev, dict) else __import__("json").loads(ev)
    assert ev["grade"] == "A" and ev["photo_url"] == d["photo_url"] and ev["version"] == d["version"]   # what the WebSocket carries
    for method in (http.head, http.get):                                     # reachable, a real image, cacheable
        r = await method(d["photo_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and "immutable" in r.headers["cache-control"]
    got = await http.get(d["photo_url"])
    assert got.content == SAMPLE and got.content[:3] == b"\xff\xd8\xff"


async def test_the_demo_board_sample_photo_is_a_real_jpeg(env):
    pool, http, h = env
    r = await http.get("/demo/sample.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content[:3] == b"\xff\xd8\xff" and r.content[-2:] == b"\xff\xd9" and len(r.content) > 5000


async def test_the_seeded_verified_paddy_cluster_has_a_real_photo():
    await demo_reset.main(empty=False, keep_farmers=False)
    pool = await db.connect()
    await cache.connect()
    try:
        async with pool.acquire() as conn:
            paddy = next(c for c in await views.cluster_list(conn) if c["crop_code"] == "paddy_common")
        assert paddy["status"] == "BIDDING" and paddy["grade"] == "B" and paddy["photo_url"].startswith("/media/v/")
        assert (settings.media_dir / "v" / paddy["photo_url"].rsplit("/", 1)[1]).read_bytes()[:3] == b"\xff\xd8\xff"
    finally:
        await cache.close()
        await db.close()
