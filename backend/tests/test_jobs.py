"""D6 integration: call queue, worker, retries and the farmer confirmation round against real Postgres + Valkey."""
import asyncio
import uuid

import asyncpg
import pytest

from app import cache, db
from app.config import settings
from app.engine.actions import Event
from app.engine.deps import PgDeps
from app.engine.service import process
from app.services import bidding, clustering, jobs
from app.telephony import base
from test_d4 import CP, PREFIX, session, setup_farmers, teardown
from test_d5 import teardown5
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


async def full_teardown() -> None:
    c = await asyncpg.connect(settings.database_url)
    await c.execute("DELETE FROM call_jobs WHERE phone LIKE $1", PREFIX + "%")
    await c.execute("DELETE FROM consent_log WHERE farmer_id IN (SELECT id FROM farmers WHERE phone LIKE $1)", PREFIX + "%")
    await c.execute("DELETE FROM dtmf_events WHERE session_id IN (SELECT id FROM call_sessions WHERE phone LIKE $1)", PREFIX + "%")
    await c.execute("DELETE FROM triage_tickets WHERE phone LIKE $1", PREFIX + "%")
    await c.close()
    await teardown5()


class FakeLine:
    """Stands in for the phone network. mode per phone: accept | reject | hangup | noanswer | offline | hold."""

    def __init__(self, deps, default="accept"):
        self.deps, self.default, self.modes, self.calls = deps, default, {}, []

    async def place_call(self, phone, job):
        self.calls.append(phone)
        mode = self.modes.get(phone, self.default)
        if mode == "offline":
            return False
        if mode == "hold":
            return True                                        # rings forever, never reports back
        if mode == "noanswer":
            await jobs.on_call_end(job["id"], answered=False)
            return True
        await jobs.mark_in_call(job["id"])
        call = "fake-" + uuid.uuid4().hex[:6]

        async def send(kind, digits=""):
            return await process(self.deps, phone, Event(kind=kind, digits=digits, call_id=call,
                                                         event_id=uuid.uuid4().hex, job=job if kind == "start" else None))
        await send("start")
        if mode == "accept":
            await send("digits", "1")
            await send("digits", "1")
        elif mode == "reject":
            await send("digits", "2")
        await jobs.on_call_end(job["id"], answered=True)
        return True


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


async def make_round(pool, qtys, bid_price=3200, min_qty=20, ask=3000):
    """Lots of the given sizes in one cluster -> BIDDING -> one bid -> auction closed (jobs queued)."""
    farmers = await setup_farmers(len(qtys))
    for i, ((p, f), q) in enumerate(zip(farmers, qtys)):
        await clustering.commit_listing(pool, session(p, f, q, ask + i))
    cid = str(await pool.fetchval("SELECT id FROM clusters WHERE collection_point_id = $1::uuid", CP))
    await pool.execute("UPDATE clusters SET status = 'BIDDING' WHERE id = $1::uuid", cid)
    buyer = str(await pool.fetchval("SELECT id FROM buyers WHERE email = 'buyer1@demo.test'"))
    bid, _ = await bidding.place_bid(pool, buyer, cid, bid_price, min_qty, "k-" + uuid.uuid4().hex[:6])
    assert await bidding.close_auction(pool, cid) == "CONFIRMING"
    return farmers, cid, bid["id"]


async def job_rows(pool, bid_id):
    return await pool.fetch("SELECT phone, status, attempts, last_error FROM call_jobs "
                            "WHERE payload->>'bid_id' = $1 ORDER BY phone", bid_id)


async def test_closing_the_auction_queues_exactly_one_call_per_lot(env):
    pool, _ = env
    farmers, cid, bid = await make_round(pool, [5] * 8)
    rows = await job_rows(pool, bid)
    assert len(rows) == 8 and {r["status"] for r in rows} == {"QUEUED"}
    assert await bidding.close_auction(pool, cid) == "CONFIRMING"           # closing again adds nothing
    assert len(await job_rows(pool, bid)) == 8


async def test_eight_lots_five_accept_makes_a_deal_of_their_quantity(env):
    pool, line = env
    farmers, cid, bid = await make_round(pool, [5] * 8, min_qty=20)
    for p, _ in farmers[5:]:
        line.modes[p] = "reject"
    await jobs.tick()
    assert len(line.calls) == 8
    deal = await pool.fetchrow("SELECT qty_qtl, price_per_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
    assert float(deal["qty_qtl"]) == 25 and float(deal["price_per_qtl"]) == 3200
    assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid) == "DEAL"
    # the three lots that said no went back into the pool for the next buyer
    pooled = await pool.fetchrow("""SELECT status, total_qtl, listing_count FROM clusters
                                    WHERE collection_point_id = $1::uuid AND status IN ('OPEN','READY')""", CP)
    assert pooled["listing_count"] == 3 and float(pooled["total_qtl"]) == 15
    assert {r["status"] for r in await job_rows(pool, bid)} == {"DONE"}
    resp = [r["response"] for r in await pool.fetch("SELECT response FROM bid_responses WHERE bid_id = $1::uuid ORDER BY id", bid)]
    assert sorted(resp) == ["ACCEPT"] * 5 + ["REJECT"] * 3


async def test_only_five_calls_run_at_once(env):
    pool, line = env
    line.default = "hold"
    farmers, cid, bid = await make_round(pool, [3] * 8, min_qty=5)
    n = await jobs.tick()
    st = [r["status"] for r in await job_rows(pool, bid)]
    assert n == 5, [(r["status"], r["attempts"], r["last_error"]) for r in await job_rows(pool, bid)]
    assert st.count("DIALING") == 5 and st.count("QUEUED") == 3
    assert await jobs.tick() == 0                                           # still full


async def test_unanswered_calls_retry_with_backoff_then_fail_and_the_round_settles_at_deadline(env):
    pool, line = env
    line.default = "noanswer"
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    for attempt in (1, 2, 3):
        await jobs.tick()
        rows = await job_rows(pool, bid)
        assert {r["attempts"] for r in rows} == {attempt}
        if attempt < 3:
            assert {r["status"] for r in rows} == {"QUEUED"} and rows[0]["last_error"] == "NO_ANSWER"
            nxt = await pool.fetchval("SELECT min(run_at) - now() FROM call_jobs WHERE payload->>'bid_id' = $1", bid)
            assert 5 < nxt.total_seconds() <= settings.job_backoff_s[attempt - 1] + 1        # 20 s, then 40 s
            await pool.execute("UPDATE call_jobs SET run_at = now() WHERE payload->>'bid_id' = $1", bid)
    assert {r["status"] for r in await job_rows(pool, bid)} == {"FAILED"}
    # nobody ever answered: at the deadline the bid fails and the cluster reopens for bidding (first failure)
    await pool.execute("UPDATE bids SET confirm_deadline = now() - interval '1 second' WHERE id = $1::uuid", bid)
    await bidding.tick(pool)
    assert await pool.fetchval("SELECT status FROM bids WHERE id = $1::uuid", bid) == "FAILED"
    assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid) == "BIDDING"
    assert {r["response"] for r in await pool.fetch("SELECT response FROM bid_responses WHERE bid_id = $1::uuid", bid)} == {"NO_ANSWER"}


async def test_offline_phone_is_retried_and_a_farmer_on_another_call_is_not_interrupted(env):
    pool, line = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    (p1, _), (p2, _) = farmers
    line.modes[p1] = "offline"
    await cache.redis.set(f"lock:call:{p2}", "other-call", px=60_000)        # p2 is on a call right now
    await jobs.tick()
    by = {r["phone"]: r for r in await job_rows(pool, bid)}
    assert by[p1]["status"] == "QUEUED" and by[p1]["last_error"] == "NO_LINE" and by[p1]["attempts"] == 1
    assert by[p2]["status"] == "QUEUED" and by[p2]["attempts"] == 0          # waited, used no attempt
    assert p2 not in line.calls


async def test_daily_call_budget_stops_the_queue(env):
    pool, line = env
    farmers, cid, bid = await make_round(pool, [10], min_qty=5)
    saved = settings.daily_call_budget
    object.__setattr__(settings, "daily_call_budget", 0)
    try:
        await jobs.tick()
    finally:
        object.__setattr__(settings, "daily_call_budget", saved)
    rows = await job_rows(pool, bid)
    assert rows[0]["status"] == "FAILED" and rows[0]["last_error"] == "BUDGET" and line.calls == []


async def test_a_lot_cannot_be_accepted_twice_and_a_settled_offer_is_not_replayed(env):
    pool, line = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    lid = str(await pool.fetchval("""SELECT l.id FROM listings l JOIN farmers f ON f.id = l.farmer_id
                                     WHERE f.phone = $1""", farmers[0][0]))
    results = await asyncio.gather(*[bidding.record_response(pool, bid, lid, "ACCEPT") for _ in range(6)])
    assert results.count(True) == 1                                        # first answer wins
    rows = await pool.fetch("SELECT response FROM bid_responses WHERE bid_id = $1::uuid AND listing_id = $2::uuid", bid, lid)
    assert [r["response"] for r in rows] == ["ACCEPT"]
    assert await PgDeps(pool).get_offer(bid, lid) is None                  # a second call is told nothing to offer
    # the reject comes too late for the same lot: still ACCEPT
    assert await bidding.record_response(pool, bid, lid, "REJECT") is False


async def test_settling_the_round_cancels_calls_not_yet_made(env):
    pool, line = env
    farmers, cid, bid = await make_round(pool, [10, 10, 10], min_qty=10)
    lots = [str(r["id"]) for r in await pool.fetch(
        """SELECT l.id FROM listings l JOIN farmers f ON f.id = l.farmer_id WHERE l.cluster_id = $1::uuid
           ORDER BY l.ask_price""", cid)]
    for lid in lots[:2]:
        await bidding.record_response(pool, bid, lid, "ACCEPT")             # two farmers answered, one never did
    await pool.execute("UPDATE bids SET confirm_deadline = now() - interval '1 second' WHERE id = $1::uuid", bid)
    await bidding.tick(pool)                                                # deadline: 20 q accepted >= min 10 -> deal
    assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid) == "DEAL"
    assert sorted(r["status"] for r in await job_rows(pool, bid)) == ["CANCELLED", "DONE", "DONE"]
    assert await jobs.tick() == 0 and line.calls == []                      # nobody is called for a settled round


async def test_stuck_calls_are_reaped_and_retried(env):
    pool, line = env
    line.default = "hold"
    farmers, cid, bid = await make_round(pool, [10], min_qty=5)
    await jobs.tick()
    await pool.execute("UPDATE call_jobs SET updated_at = now() - interval '10 minutes' WHERE payload->>'bid_id' = $1", bid)
    line.default = "accept"
    await pool.execute("UPDATE call_jobs SET status = 'QUEUED', run_at = now() WHERE false")       # no-op, keeps intent clear
    await jobs.tick()                                                       # reaps -> QUEUED with backoff
    assert (await job_rows(pool, bid))[0]["status"] == "QUEUED"
    await pool.execute("UPDATE call_jobs SET run_at = now() WHERE payload->>'bid_id' = $1", bid)
    await jobs.tick()
    assert (await job_rows(pool, bid))[0]["status"] == "DONE"
    assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid) == "DEAL"


def test_simulator_phone_rings_for_the_offer_and_accepting_it_makes_the_deal():
    """End to end over the real WebSocket: queue -> worker -> ring -> answer -> keys 1,1 -> deal."""
    from fastapi.testclient import TestClient
    from app.main import app

    asyncio.run(full_teardown())
    farmers = asyncio.run(setup_farmers(1))
    phone = farmers[0][0]
    try:
        with TestClient(app) as client:
            async def prepare():
                await clustering.commit_listing(db.pool, session(phone, farmers[0][1], 25, 3000))
                cid = str(await db.pool.fetchval("SELECT id FROM clusters WHERE collection_point_id = $1::uuid", CP))
                await db.pool.execute("UPDATE clusters SET status = 'BIDDING' WHERE id = $1::uuid", cid)
                buyer = str(await db.pool.fetchval("SELECT id FROM buyers WHERE email = 'buyer1@demo.test'"))
                await bidding.place_bid(db.pool, buyer, cid, 3100, 20, "ws-" + uuid.uuid4().hex[:6])
                return cid
            cid = client.portal.call(prepare)
            with client.websocket_connect(f"/tel/sim/ws?phone={phone.replace('+', '%2B')}") as ws:
                client.portal.call(bidding.close_auction, db.pool, cid)       # the worker (1 s tick) rings this phone
                ring = ws.receive_json()
                assert ring["t"] == "ring"
                ws.send_json({"t": "answer", "call_id": ring["call_id"]})
                play = ws.receive_json()
                assert play["t"] == "play" and play["state"] == "OFFER"
                ws.send_json({"t": "digit", "call_id": ring["call_id"], "d": "1", "ts_ms": 1000, "seq": 1})
                assert ws.receive_json()["state"] == "OFFER_CONFIRM"
                ws.send_json({"t": "digit", "call_id": ring["call_id"], "d": "1", "ts_ms": 3000, "seq": 2})
                done = ws.receive_json()
                assert done["state"] == "DONE_OFFER"
                assert ws.receive_json()["t"] == "hangup"
            deal = client.portal.call(db.pool.fetchrow, "SELECT qty_qtl, price_per_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
            assert float(deal["qty_qtl"]) == 25 and float(deal["price_per_qtl"]) == 3100
            job = client.portal.call(db.pool.fetchval, "SELECT status FROM call_jobs WHERE phone = $1", phone)
            assert job in ("DONE", "CANCELLED")
    finally:
        asyncio.run(full_teardown())
