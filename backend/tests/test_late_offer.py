"""A farmer who answers after the round has settled is told so (never "Accepted"); a farmer still on the phone when the
window ends gets a short grace. Real Postgres + Valkey (test database)."""
import json
import uuid

import pytest

from app import cache, db
from app.engine.actions import Event
from app.engine.deps import PgDeps
from app.engine.service import process
from app.services import bidding
from test_jobs import full_teardown, make_round
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await full_teardown()
    yield pool, PgDeps(pool)
    await full_teardown()
    await cache.close()
    await db.close()


async def job_of(pool, phone, bid):
    r = await pool.fetchrow("SELECT id::text, kind, payload FROM call_jobs WHERE phone = $1 AND payload->>'bid_id' = $2", phone, bid)
    payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
    return {"id": r["id"], "kind": r["kind"], "payload": payload}


async def press(deps, phone, call, digits):
    return await process(deps, phone, Event(kind="digits", digits=digits, call_id=call, event_id=uuid.uuid4().hex))


async def start(deps, pool, phone, bid):
    call = "late-" + uuid.uuid4().hex[:6]
    a = await process(deps, phone, Event(kind="start", call_id=call, event_id=uuid.uuid4().hex, job=await job_of(pool, phone, bid)))
    assert a.state == "OFFER"
    return call


async def test_an_accept_after_the_round_settled_is_not_recorded_and_not_confirmed_to_the_farmer(env):
    pool, deps = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    (slow, _), (other, _) = farmers
    call = await start(deps, pool, slow, bid)
    assert (await press(deps, slow, call, "1")).state == "OFFER_CONFIRM"            # the farmer is mid-confirmation...
    await pool.execute("UPDATE bids SET confirm_deadline = now() - interval '5 minutes' WHERE id = $1::uuid", bid)
    await bidding.tick(pool)                                                         # ...the window ends, past any grace
    assert await pool.fetchval("SELECT status FROM bids WHERE id = $1::uuid", bid) == "FAILED"
    late = await press(deps, slow, call, "1")                                       # the late final "1"
    assert late.hangup and late.clips == ["offer_closed"]                           # NOT "offer_done" ("Accepted...")
    assert "offer_done" not in late.clips
    rows = {r["phone"]: r["response"] for r in await pool.fetch(
        "SELECT f.phone, r.response FROM bid_responses r JOIN listings l ON l.id = r.listing_id JOIN farmers f ON f.id = l.farmer_id "
        "WHERE r.bid_id = $1::uuid", bid)}
    assert rows[slow] == "NO_ANSWER" and await pool.fetchval("SELECT count(*) FROM deals") == 0   # nothing was recorded


async def test_a_farmer_still_on_the_phone_at_the_deadline_gets_a_grace_and_the_deal_forms(env):
    pool, deps = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    (slow, _), (other, _) = farmers
    call = await start(deps, pool, slow, bid)
    await press(deps, slow, call, "1")
    await pool.execute("UPDATE call_jobs SET status = 'IN_CALL' WHERE phone = $1 AND payload->>'bid_id' = $2", slow, bid)
    await pool.execute("UPDATE bids SET confirm_deadline = now() - interval '5 seconds' WHERE id = $1::uuid", bid)   # just past the deadline
    await bidding.tick(pool)
    assert await pool.fetchval("SELECT status FROM bids WHERE id = $1::uuid", bid) == "CONFIRMING"   # the round waits for the caller
    done = await press(deps, slow, call, "1")                                       # the caller finishes in time (inside the grace)
    assert done.state == "DONE_OFFER" and done.clips == ["offer_done"]
    assert await pool.fetchval("""SELECT r.response FROM bid_responses r JOIN listings l ON l.id = r.listing_id
                                  JOIN farmers f ON f.id = l.farmer_id WHERE r.bid_id = $1::uuid AND f.phone = $2""", bid, slow) == "ACCEPT"
    await pool.execute("UPDATE call_jobs SET status = 'DONE' WHERE phone = $1 AND payload->>'bid_id' = $2", slow, bid)   # call over
    await bidding.tick(pool)                                                         # the other lot never answered: 10 q >= minimum 10
    deal = await pool.fetchrow("SELECT qty_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
    assert float(deal["qty_qtl"]) == 10


async def test_the_grace_is_limited_to_two_minutes(env):
    pool, deps = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    (stuck, _), _ = farmers
    await pool.execute("UPDATE call_jobs SET status = 'IN_CALL' WHERE phone = $1 AND payload->>'bid_id' = $2", stuck, bid)
    await pool.execute("UPDATE bids SET confirm_deadline = now() - interval '3 minutes' WHERE id = $1::uuid", bid)
    await bidding.tick(pool)                                                         # a call that never ends cannot hold the round open
    assert await pool.fetchval("SELECT status FROM bids WHERE id = $1::uuid", bid) == "FAILED"


async def test_repeating_the_same_key_is_not_mistaken_for_a_late_answer(env):
    pool, deps = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=20)
    (a, _), _ = farmers
    call = await start(deps, pool, a, bid)
    await press(deps, a, call, "1")
    assert (await press(deps, a, call, "1")).state == "DONE_OFFER"
    lot = await pool.fetchval("""SELECT l.id::text FROM listings l JOIN farmers f ON f.id = l.farmer_id
                                 WHERE f.phone = $1 AND l.cluster_id = $2::uuid""", a, cid)
    assert await deps.record_offer_response(bid, lot, "ACCEPT") is True              # the same answer again: still fine
    assert await deps.record_offer_response(bid, lot, "REJECT") is False             # a different one after the first: refused
