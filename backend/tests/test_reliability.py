"""D3 reliability tests against the real Postgres + Valkey from docker compose (skipped if they are not up).

Each test uses its own throw-away farmer, so the dev data and other tests are untouched.
"""
import asyncio
import json
import random
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
import redis.asyncio as aioredis

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dev_min_seed as seed  # noqa: E402

from app import cache, db  # noqa: E402
from app.config import settings  # noqa: E402
from app.engine import guard, session as store  # noqa: E402
from app.engine.actions import Event  # noqa: E402
from app.engine.deps import PgDeps  # noqa: E402
from app.engine.service import process  # noqa: E402


async def _probe() -> None:
    c = await asyncpg.connect(settings.database_url, timeout=3)
    await c.close()
    r = aioredis.from_url(settings.redis_url)
    await r.ping()
    await r.aclose()


try:
    asyncio.run(_probe())
    STACK_UP = True
except Exception:
    STACK_UP = False

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


async def make_farmer() -> str:
    await seed.main(None, False)                       # reference rows (idempotent)
    phone = f"+9199{random.randint(10_000_000, 99_999_999)}"
    c = await asyncpg.connect(settings.database_url)
    await c.execute("""INSERT INTO farmers (phone,name,fpo_id,village,district_code,geog,collection_point_id,lang,
                          consent_version,consent_at)
        VALUES ($1,'Test Farmer',$2::uuid,'Testgram','KA-MANDYA',
                ST_SetSRID(ST_MakePoint(76.91,12.53),4326)::geography,$3::uuid,'kn','v1',now())""",
                    phone, seed.FPO_ID, seed.CP_ID)
    await c.close()
    return phone


async def cleanup(phone: str) -> None:
    c = await asyncpg.connect(settings.database_url)
    await c.execute("DELETE FROM dtmf_events WHERE session_id IN (SELECT id FROM call_sessions WHERE phone=$1)", phone)
    await c.execute("DELETE FROM listings WHERE farmer_id IN (SELECT id FROM farmers WHERE phone=$1)", phone)
    await c.execute("DELETE FROM call_sessions WHERE phone=$1", phone)
    await c.execute("DELETE FROM triage_tickets WHERE phone=$1", phone)
    await c.execute("DELETE FROM consent_log WHERE farmer_id IN (SELECT id FROM farmers WHERE phone=$1)", phone)
    await c.execute("DELETE FROM farmers WHERE phone=$1", phone)
    await c.execute("DELETE FROM clusters c WHERE NOT EXISTS (SELECT 1 FROM listings l WHERE l.cluster_id=c.id)")
    await c.close()
    r = aioredis.from_url(settings.redis_url)
    for k in await r.keys(f"*{phone}*"):
        await r.delete(k)
    await r.aclose()


async def fetch(sql: str, *args):
    c = await asyncpg.connect(settings.database_url)
    try:
        return await c.fetch(sql, *args)
    finally:
        await c.close()


@pytest.fixture
async def stack():
    pool = await db.connect()
    await cache.connect()
    phone = await make_farmer()
    yield PgDeps(pool), phone
    await cleanup(phone)
    await cache.close()
    await db.close()


async def ev(deps, phone, kind, digits="", call="c1", eid=None):
    return await process(deps, phone, Event(kind=kind, digits=digits, call_id=call, event_id=eid or uuid.uuid4().hex))


async def test_flushall_mid_call_continues_from_checkpoint(stack):
    deps, phone = stack
    assert (await ev(deps, phone, "start")).state == "CROP"
    assert (await ev(deps, phone, "digits", "1")).state == "QTY"
    assert (await ev(deps, phone, "digits", "17")).state == "QTY_CONFIRM"
    row = (await fetch("SELECT state, version FROM call_sessions WHERE phone=$1", phone))[0]
    assert row["state"] == "QTY_CONFIRM"

    await cache.redis.flushdb()                       # Valkey loses everything mid-call
    cache.load_scripts()
    assert await cache.redis.get(f"sess:{phone}") is None

    assert (await ev(deps, phone, "digits", "1")).state == "PRICE"       # the next key just works
    assert (await ev(deps, phone, "digits", "3600")).state == "FINAL"
    done = await ev(deps, phone, "digits", "1")
    assert done.state == "DONE" and done.hangup
    q = await fetch("""SELECT qty_qtl, ask_price FROM listings l JOIN farmers f ON f.id=l.farmer_id
                       WHERE f.phone=$1""", phone)
    assert len(q) == 1 and float(q[0]["qty_qtl"]) == 17 and float(q[0]["ask_price"]) == 3600
    assert (await fetch("SELECT outcome FROM call_sessions WHERE phone=$1", phone))[0]["outcome"] == "COMPLETED"


async def test_stale_checkpoint_is_not_rehydrated(stack):
    deps, phone = stack
    await ev(deps, phone, "start")
    await ev(deps, phone, "digits", "1")
    c = await asyncpg.connect(settings.database_url)
    await c.execute("UPDATE call_sessions SET updated_at = now() - interval '31 minutes' WHERE phone=$1", phone)
    await c.close()
    await cache.redis.flushdb()
    assert await store.load(phone) is None             # older than 30 minutes: the draft is gone
    assert await store.expire_stale() >= 1
    assert (await fetch("SELECT outcome FROM call_sessions WHERE phone=$1", phone))[0]["outcome"] == "EXPIRED"


async def test_duplicate_event_is_applied_once(stack):
    deps, phone = stack
    await ev(deps, phone, "start")
    for digits in ("1", "17", "1", "3600"):
        await ev(deps, phone, "digits", digits)
    first = await ev(deps, phone, "digits", "1", eid="same-event")       # FINAL: commit
    again = await ev(deps, phone, "digits", "1", eid="same-event")       # webhook retry
    assert first.state == "DONE" and again.hangup_now
    assert len(await fetch("SELECT 1 FROM listings l JOIN farmers f ON f.id=l.farmer_id WHERE f.phone=$1", phone)) == 1
    assert len(await fetch("""SELECT 1 FROM dtmf_events e JOIN call_sessions s ON s.id=e.session_id
                              WHERE s.phone=$1 AND e.event_id='same-event'""", phone)) == 1


async def test_duplicate_mid_call_event_replays_prompt_without_advancing(stack):
    deps, phone = stack
    await ev(deps, phone, "start")
    await ev(deps, phone, "digits", "1")
    a = await ev(deps, phone, "digits", "17", eid="e1")
    v = (await store.load(phone))["version"]
    b = await ev(deps, phone, "digits", "17", eid="e1")
    assert a.state == b.state == "QTY_CONFIRM" and (await store.load(phone))["version"] == v


async def test_three_failed_calls_open_exactly_one_ticket(stack):
    deps, phone = stack
    last = None
    for call in range(3):
        await ev(deps, phone, "start", call=f"call{call}")
        for _ in range(3):                             # three invalid keys at the crop menu
            last = await ev(deps, phone, "digits", "9", call=f"call{call}")
    assert last.state == "HELP" and last.hangup
    tickets = await fetch("SELECT verbal_code, reason, status FROM triage_tickets WHERE phone=$1", phone)
    assert len(tickets) == 1 and tickets[0]["reason"] == "IVR_FAIL_3" and tickets[0]["status"] == "OPEN"
    assert last.clips[-2:] == [f"d_{c}" for c in tickets[0]["verbal_code"]]     # the IVR spoke the stored code
    assert [r["outcome"] for r in await fetch(
        "SELECT outcome FROM call_sessions WHERE phone=$1 ORDER BY started_at", phone)] == [
        "FAILED_INPUT", "FAILED_INPUT", "FAILED_INPUT"]


async def test_missed_call_dedupe_and_rate_limits(stack):
    _, phone = stack
    assert await guard.accept_missed_call(phone, 3, 6) == "ok"
    assert await guard.accept_missed_call(phone, 3, 6) == "DUPLICATE"      # within 20 s
    for _ in range(2):
        await cache.redis.delete(f"miss:{phone}")
        assert await guard.accept_missed_call(phone, 3, 6) == "ok"
    await cache.redis.delete(f"miss:{phone}")
    assert await guard.accept_missed_call(phone, 3, 6) == "RATE_LIMITED"   # 4th in 10 minutes


async def test_daily_limit_and_global_budget(stack):
    _, phone = stack
    for _ in range(6):
        await cache.redis.delete(f"miss:{phone}", f"rl:cb:{phone}:10m")
        assert await guard.accept_missed_call(phone, 99, 6) == "ok"
    await cache.redis.delete(f"miss:{phone}", f"rl:cb:{phone}:10m")
    assert await guard.accept_missed_call(phone, 99, 6) == "RATE_LIMITED"   # 7th today
    other = f"{phone}-b"
    object.__setattr__(settings, "daily_call_budget", 0)
    try:
        assert await guard.accept_missed_call(other, 3, 6) == "BUDGET"
    finally:
        object.__setattr__(settings, "daily_call_budget", int(settings.__class__.daily_call_budget))
        await cache.redis.delete(f"miss:{other}")


async def test_call_lock_is_exclusive_and_owner_released(stack):
    _, phone = stack
    assert await guard.acquire_lock(phone, "A")
    assert not await guard.acquire_lock(phone, "B")
    await guard.release_lock(phone, "B")               # not the owner: no effect
    assert not await guard.acquire_lock(phone, "B")
    await guard.release_lock(phone, "A")
    assert await guard.acquire_lock(phone, "B")


def test_bounce_over_websocket_stores_3_not_33_and_logs_it():
    from fastapi.testclient import TestClient
    from app.main import app

    phone = asyncio.run(make_farmer())
    saved = (settings.sim_ring_min, settings.sim_ring_max)
    object.__setattr__(settings, "sim_ring_min", 0.0)
    object.__setattr__(settings, "sim_ring_max", 0.01)
    try:
        with TestClient(app) as client, client.websocket_connect(f"/tel/sim/ws?phone={phone.replace('+', '%2B')}") as ws:
            ws.send_json({"t": "missed_call"})
            cid = ws.receive_json()["call_id"]
            ws.send_json({"t": "answer", "call_id": cid})
            assert ws.receive_json()["state"] == "CROP"

            def key(d, ts, seq):
                ws.send_json({"t": "digit", "call_id": cid, "d": d, "ts_ms": ts, "seq": seq})

            key("1", 1000, 1)
            assert ws.receive_json()["state"] == "QTY"
            key("3", 2000, 2)
            key("3", 2030, 3)                      # bounce: same digit 30 ms later
            key("#", 3000, 4)
            assert ws.receive_json()["state"] == "QTY_CONFIRM"
            key("1", 4000, 5)
            key("1", 4000, 5)                      # retransmitted message (same seq)
            assert ws.receive_json()["state"] == "PRICE"
        rows = asyncio.run(fetch("""SELECT s.data, array_agg(e.dropped_reason) FILTER (WHERE e.dropped_reason IS NOT NULL)
                                    AS drops FROM call_sessions s LEFT JOIN dtmf_events e ON e.session_id=s.id
                                    WHERE s.phone=$1 GROUP BY s.id""", phone))
        data = rows[0]["data"] if isinstance(rows[0]["data"], dict) else json.loads(rows[0]["data"])
        assert data["qty"] == 3
        assert rows[0]["drops"] == ["BOUNCE"]
    finally:
        object.__setattr__(settings, "sim_ring_min", saved[0])
        object.__setattr__(settings, "sim_ring_max", saved[1])
        asyncio.run(cleanup(phone))
