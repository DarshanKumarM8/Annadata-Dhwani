"""Durable outbound-call queue (table call_jobs). Owner: Darshan.

close_auction() queues one BID_OFFER job per lot. The worker claims due jobs with FOR UPDATE SKIP LOCKED, never runs more
than job_max_parallel calls, skips a farmer who is already on a call (lock:call:{phone}), honours the daily call budget,
and retries unanswered calls with backoff (demo 20/40/60 s, real 2/10/30 min). A call only counts as DONE when the farmer
actually answered the offer; a call that ended without an answer is retried. Jobs stuck in a call state are reaped.
State survives a restart because everything is in Postgres.
"""
import asyncio
import json
import logging
import time

from .. import cache, db
from ..config import settings
from ..telephony import base

log = logging.getLogger("jobs")
STUCK_S = 300
LOCK_RETRY_S = 15

CLAIM = """UPDATE call_jobs SET status = 'DIALING', attempts = attempts + 1, updated_at = now()
           WHERE id = (SELECT id FROM call_jobs WHERE status = 'QUEUED' AND run_at <= now()
                       ORDER BY run_at FOR UPDATE SKIP LOCKED LIMIT 1)
           RETURNING id::text, phone, kind, payload, attempts, max_attempts"""


def _payload(j) -> dict:
    return j["payload"] if isinstance(j["payload"], dict) else json.loads(j["payload"])


async def enqueue_bid_offers(conn, bid_id, cluster_id) -> int:
    """Called inside the close_auction transaction: one job per ACTIVE lot in the cluster."""
    r = await conn.execute("""
        INSERT INTO call_jobs (phone, farmer_id, kind, payload, dedupe_key)
        SELECT f.phone, f.id, 'BID_OFFER', jsonb_build_object('bid_id', $1::text, 'listing_id', l.id::text),
               'bid:' || $1::text || ':' || l.id::text
        FROM listings l JOIN farmers f ON f.id = l.farmer_id
        WHERE l.cluster_id = $2::uuid AND l.status = 'ACTIVE'
        ON CONFLICT (dedupe_key) DO NOTHING""", str(bid_id), str(cluster_id))
    return int(r.split()[-1])


async def enqueue_callback(conn, phone: str, farmer_id, call_sid: str) -> bool:
    """A farmer's missed call: queue the callback (a couple of seconds later, so the missed-call leg has ended)."""
    r = await conn.execute("""INSERT INTO call_jobs (phone, farmer_id, kind, payload, dedupe_key, run_at)
                              VALUES ($1, $2::uuid, 'CALLBACK', jsonb_build_object('call_sid', $3::text), $4,
                                      now() + interval '2 seconds') ON CONFLICT (dedupe_key) DO NOTHING""",
                           phone, str(farmer_id) if farmer_id else None, call_sid, f"cb:{call_sid}")
    return r.endswith("1")


async def cancel_for_bid(conn, bid_id) -> None:
    """Round settled: stop calling. A call whose lot already answered finishes as DONE, the rest as CANCELLED."""
    await conn.execute("""
        UPDATE call_jobs j SET updated_at = now(), status = CASE WHEN EXISTS (
            SELECT 1 FROM bid_responses r WHERE r.bid_id = $1::uuid AND r.listing_id = (j.payload->>'listing_id')::uuid
            AND r.response IN ('ACCEPT','REJECT')) THEN 'DONE' ELSE 'CANCELLED' END
        WHERE j.kind = 'BID_OFFER' AND j.payload->>'bid_id' = $1 AND j.status IN ('QUEUED','DIALING','IN_CALL')""",
                       str(bid_id))


def _backoff(attempts: int) -> int:
    b = settings.job_backoff_s
    return b[min(max(attempts, 1), len(b)) - 1]


async def _retry_or_fail(job_id: str, attempts: int, max_attempts: int, why: str) -> str:
    if attempts >= max_attempts:
        await db.pool.execute("UPDATE call_jobs SET status = 'FAILED', last_error = $2, updated_at = now() "
                              "WHERE id = $1::uuid", job_id, why)
        return "FAILED"
    await db.pool.execute("""UPDATE call_jobs SET status = 'QUEUED', last_error = $2, updated_at = now(),
                             run_at = now() + make_interval(secs => $3) WHERE id = $1::uuid""",
                          job_id, why, float(_backoff(attempts)))
    return "QUEUED"


async def _offer_open(payload: dict) -> bool:
    """Is this lot still waiting for an answer on a bid that is still being confirmed?"""
    return bool(await db.pool.fetchval("""
        SELECT 1 FROM bid_responses r JOIN bids b ON b.id = r.bid_id
        WHERE r.bid_id = $1::uuid AND r.listing_id = $2::uuid AND r.response = 'PENDING' AND b.status = 'CONFIRMING'""",
                                       payload["bid_id"], payload["listing_id"]))


async def mark_in_call(job_id: str) -> None:
    await db.pool.execute("UPDATE call_jobs SET status = 'IN_CALL', updated_at = now() "
                          "WHERE id = $1::uuid AND status = 'DIALING'", job_id)


async def on_call_end(job_id: str, answered: bool = True) -> str | None:
    """Provider callback when the call is over (or was never answered). Decides DONE / retry / FAILED."""
    j = await db.pool.fetchrow("SELECT kind, payload, attempts, max_attempts, status FROM call_jobs WHERE id = $1::uuid",
                               job_id)
    if not j or j["status"] not in ("DIALING", "IN_CALL"):
        return None
    if j["kind"] == "CALLBACK":                 # the farmer picked up: the call did its job
        if answered:
            await db.pool.execute("UPDATE call_jobs SET status = 'DONE', updated_at = now() WHERE id = $1::uuid", job_id)
            return "DONE"
        return await _retry_or_fail(job_id, j["attempts"], j["max_attempts"], "NO_ANSWER")
    if not await _offer_open(_payload(j)):      # answered, or the round was settled meanwhile
        await db.pool.execute("UPDATE call_jobs SET status = 'DONE', updated_at = now() WHERE id = $1::uuid", job_id)
        return "DONE"
    return await _retry_or_fail(job_id, j["attempts"], j["max_attempts"], "NO_RESPONSE" if answered else "NO_ANSWER")


async def _dispatch(job: dict) -> None:
    payload, phone = _payload(job), job["phone"]
    offer = job["kind"] == "BID_OFFER"
    if offer and not await _offer_open(payload):
        await db.pool.execute("UPDATE call_jobs SET status = 'CANCELLED', updated_at = now() WHERE id = $1::uuid",
                              job["id"])
        return
    if await cache.redis.exists(f"lock:call:{phone}"):       # farmer is on another call: wait, no attempt used
        await db.pool.execute("""UPDATE call_jobs SET status = 'QUEUED', attempts = attempts - 1, updated_at = now(),
                                 run_at = now() + make_interval(secs => $2) WHERE id = $1::uuid""",
                              job["id"], float(LOCK_RETRY_S))
        return
    budget = f"budget:calls:{time.strftime('%Y%m%d')}"      # callbacks were already counted when the missed call was accepted
    if offer and await cache.redis.incr(budget) > settings.daily_call_budget:
        await cache.redis.decr(budget)
        await db.pool.execute("UPDATE call_jobs SET status = 'FAILED', last_error = 'BUDGET', updated_at = now() "
                              "WHERE id = $1::uuid", job["id"])
        return
    provider = base.get_provider(phone)
    if getattr(provider, "name", "") == "exotel" and phone[-10:].startswith("980000"):
        # the seeded demo farmers (+91 98000000xx) and agents are made-up numbers that may belong to real people:
        # the real network never dials them, whatever TEAM_PHONES says
        await db.pool.execute("UPDATE call_jobs SET status = 'FAILED', last_error = 'SIMULATED_NUMBER', updated_at = now() "
                              "WHERE id = $1::uuid", job["id"])
        if offer:
            await cache.redis.decr(budget)
        return
    if getattr(provider, "name", "") == "exotel" and settings.team_phones and phone[-10:] not in settings.team_phones:
        # never dial a stranger or a made-up number from a trial setup: only the numbers listed in TEAM_PHONES
        await db.pool.execute("UPDATE call_jobs SET status = 'FAILED', last_error = 'NOT_WHITELISTED', updated_at = now() "
                              "WHERE id = $1::uuid", job["id"])
        if offer:
            await cache.redis.decr(budget)
        return
    try:
        placed = await provider.place_call(phone, {"id": job["id"], "kind": job["kind"], "payload": payload})
    except Exception:
        log.exception("place_call failed")
        placed = False
    if not placed:
        if offer:
            await cache.redis.decr(budget)
        await _retry_or_fail(job["id"], job["attempts"], job["max_attempts"], "NO_LINE")


async def tick() -> int:
    """One worker pass. Returns the number of calls started."""
    for r in await db.pool.fetch("""SELECT id::text FROM call_jobs WHERE status IN ('DIALING','IN_CALL')
                                    AND updated_at < now() - make_interval(secs => $1)""", float(STUCK_S)):
        await on_call_end(r["id"], answered=False)             # reap calls the provider never reported on
    started = 0
    while True:
        active = await db.pool.fetchval("SELECT count(*) FROM call_jobs WHERE status IN ('DIALING','IN_CALL')")
        if active >= settings.job_max_parallel:
            break
        row = await db.pool.fetchrow(CLAIM)
        if not row:
            break
        await _dispatch(dict(row))
        started += 1
    return started


async def run(interval_s: float = 1.0) -> None:
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("job worker pass failed")
        await asyncio.sleep(interval_s)
