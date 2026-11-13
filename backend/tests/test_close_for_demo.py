"""close_for_demo: only real phones are called; simulator farmers answer for themselves; the deal still forms."""
import uuid

import pytest

import close_for_demo
from app import cache, db
from app.services import bidding, clustering, jobs
from app.telephony import base
from test_d4 import CP, session, setup_farmers
from test_jobs import FakeLine, full_teardown
from test_reliability import STACK_UP
from app.engine.deps import PgDeps

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await full_teardown()
    line = FakeLine(PgDeps(pool))
    base.set_provider(line)
    yield pool, line
    base.set_provider(None)
    await full_teardown()
    await cache.close()
    await db.close()


async def bidding_cluster(pool, n=3, qty=10, min_qty=20):
    farmers = await setup_farmers(n)
    for i, (p, f) in enumerate(farmers):
        await clustering.commit_listing(pool, session(p, f, qty, 3000 + i))
    cid = str(await pool.fetchval("SELECT id FROM clusters WHERE collection_point_id = $1::uuid", CP))
    await pool.execute("UPDATE clusters SET status = 'BIDDING' WHERE id = $1::uuid", cid)
    buyer = str(await pool.fetchval("SELECT id FROM buyers WHERE email = 'buyer1@demo.test'"))
    await bidding.place_bid(pool, buyer, cid, 3200, min_qty, "k-" + uuid.uuid4().hex[:6])
    return farmers, cid


async def test_simulator_lots_are_never_dialed_and_the_real_phone_completes_the_deal(env):
    pool, line = env
    farmers, cid = await bidding_cluster(pool)
    (sim1, _), (sim2, _), (real, _) = farmers

    async def closer(c):
        assert await bidding.close_auction(pool, c) == "CONFIRMING"

    out = await close_for_demo.close_with_simulated_farmers(pool, cid, closer, sim_phones={sim1, sim2})
    assert out["simulated"] == 2 and out["real"] == [real] and out["sim_qtl"] == 20 and out["real_qtl"] == 10
    await jobs.tick()                                                       # the worker now runs
    assert line.calls == [real]                                             # ONLY the real phone was called
    deal = await pool.fetchrow("SELECT qty_qtl, price_per_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
    assert float(deal["qty_qtl"]) == 30 and float(deal["price_per_qtl"]) == 3200
    sim_jobs = await pool.fetch("SELECT status, last_error FROM call_jobs WHERE phone = ANY($1)", [sim1, sim2])
    assert {r["status"] for r in sim_jobs} == {"CANCELLED"} and {r["last_error"] for r in sim_jobs} == {"SIMULATED_FARMER"}


async def test_a_cluster_without_a_bid_or_not_bidding_is_left_alone(env):
    pool, _ = env
    farmers = await setup_farmers(2)
    for i, (p, f) in enumerate(farmers):
        await clustering.commit_listing(pool, session(p, f, 15, 3000 + i))     # 30 q: READY, never verified, no bid
    cid = str(await pool.fetchval("SELECT id FROM clusters WHERE collection_point_id = $1::uuid", CP))
    closed = []
    out = await close_for_demo.close_with_simulated_farmers(pool, cid, lambda c: closed.append(c) or bidding.close_auction(pool, c))
    assert "error" in out and closed == []
    assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid) == "READY"
    assert await pool.fetchval("SELECT count(*) FROM call_jobs WHERE phone = ANY($1)", [p for p, _ in farmers]) == 0


async def test_simulated_farmers_can_be_made_to_refuse(env):
    pool, line = env
    farmers, cid = await bidding_cluster(pool, n=2, qty=10, min_qty=10)
    (sim, _), (real, _) = farmers
    await close_for_demo.close_with_simulated_farmers(pool, cid, lambda c: bidding.close_auction(pool, c),
                                                      sim_phones={sim}, accept=False)
    await jobs.tick()                                                       # the real farmer accepts: 10 q >= minimum 10
    deal = await pool.fetchrow("SELECT qty_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
    assert float(deal["qty_qtl"]) == 10 and line.calls == [real]
