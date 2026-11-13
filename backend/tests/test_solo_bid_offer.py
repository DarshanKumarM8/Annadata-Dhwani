"""solo_test_bid_offer.py end to end on the test database: one real phone, simulator farmers answered without any dial."""
import httpx
import pytest

import demo_reset
import solo_test_bid_offer as solo
from app import cache, db
from app.config import settings
from app.engine.deps import PgDeps
from app.main import app
from app.services import jobs
from app.telephony import base
from test_jobs import FakeLine
from test_reliability import STACK_UP, make_farmer
import asyncpg

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


async def wipe(phone=None):
    c = await asyncpg.connect(settings.database_url)
    for q in demo_reset.WIPE:
        await c.execute(q)
    if phone:
        await c.execute("DELETE FROM farmers WHERE phone = $1", phone)
    await c.close()


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await wipe()
    line = FakeLine(PgDeps(pool))
    base.set_provider(line)
    saved = settings.team_phones
    yield pool, line
    object.__setattr__(settings, "team_phones", saved)
    base.set_provider(None)
    await wipe()
    await cache.close()
    await db.close()


async def test_whole_chain_rings_only_the_real_phone_and_the_deal_depends_on_its_answer(env):
    pool, line = env
    phone = await make_farmer()                                     # a real-looking farmer at the same yard as the simulators
    object.__setattr__(settings, "team_phones", frozenset({phone[-10:]}))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
            r = await solo.run(pool, http, phone, 3850, poll_s=0, say=lambda *_: None)
        cid = r["cluster_id"]
        st = await pool.fetchrow("SELECT status, total_qtl FROM clusters WHERE id = $1::uuid", cid)
        assert st["status"] == "CONFIRMING" and float(st["total_qtl"]) == 20           # topped up with 3 simulator lots
        assert r["bid_price"] == 3850 and r["min_qty"] == 20
        assert await pool.fetchval("SELECT count(*) FROM verifications WHERE cluster_id = $1::uuid", cid) == 1   # via the real endpoint
        resp = [x["response"] for x in await pool.fetch("""SELECT response FROM bid_responses WHERE bid_id = $1::uuid ORDER BY id""", r["bid_id"])]
        assert sorted(resp) == ["ACCEPT", "ACCEPT", "ACCEPT", "PENDING"]                # simulators answered, the real farmer has not
        assert await pool.fetchval("SELECT count(*) FROM deals") == 0

        await jobs.tick()                                           # the server's worker: rings the real phone, who accepts
        assert line.calls == [phone]                                # no simulator number was ever dialed
        deal = await pool.fetchrow("SELECT qty_qtl, price_per_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
        assert float(deal["qty_qtl"]) == 20 and float(deal["price_per_qtl"]) == 3850
        sim_jobs = await pool.fetch("SELECT status, last_error FROM call_jobs WHERE phone LIKE '+91980000%'")
        assert len(sim_jobs) == 3 and {j["status"] for j in sim_jobs} == {"CANCELLED"}
    finally:
        await wipe(phone)


async def test_the_real_farmer_refusing_means_no_deal(env):
    pool, line = env
    phone = await make_farmer()
    line.modes[phone] = "reject"
    object.__setattr__(settings, "team_phones", frozenset({phone[-10:]}))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
            r = await solo.run(pool, http, phone, 3850, poll_s=0, say=lambda *_: None)
        await jobs.tick()
        assert await pool.fetchval("SELECT count(*) FROM deals") == 0
        assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", r["cluster_id"]) == "BIDDING"   # reopens once
    finally:
        await wipe(phone)


async def test_the_script_refuses_numbers_it_must_not_dial(env):
    pool, _ = env
    with pytest.raises(solo.Stop, match="seeded demo number"):
        await solo.pick_phone(pool, "+919800000001")
    object.__setattr__(settings, "team_phones", frozenset({"9000000001"}))
    with pytest.raises(solo.Stop, match="not in TEAM_PHONES"):
        await solo.pick_phone(pool, "+919812345678")
    assert await solo.pick_phone(pool, "09000000001") == "+919000000001"          # a leading 0 is normalised


async def test_a_lot_stranded_in_a_no_bid_cluster_is_released_and_relisted(env):
    pool, line = env
    phone = await make_farmer()
    object.__setattr__(settings, "team_phones", frozenset({phone[-10:]}))
    try:
        fid = await solo.ensure_farmer(pool, phone)
        await solo.commit_lot(pool, phone, fid, 5, 3600)
        old = await solo.my_cluster(pool, fid)
        await pool.execute("UPDATE clusters SET status = 'NO_BID' WHERE id = $1::uuid", old["id"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as http:
            r = await solo.run(pool, http, phone, 3850, poll_s=0, say=lambda *_: None)
        assert r["cluster_id"] != old["id"]                                          # a new cluster, not the dead one
        assert await pool.fetchval("SELECT status FROM listings WHERE cluster_id = $1::uuid AND farmer_id = $2::uuid", old["id"], fid) == "WITHDRAWN"
        assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", r["cluster_id"]) == "CONFIRMING"
    finally:
        await wipe(phone)
