"""reset_caller.py: a phone goes back to a brand-new first-time farmer; lots in a running auction are never touched."""
import pytest

import reset_caller
from app import cache, db
from app.services import clustering
from test_d4 import CP, session, setup_farmers
from test_d5 import teardown5
from test_jobs import full_teardown
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await full_teardown()
    yield pool
    await full_teardown()
    await cache.close()
    await db.close()


async def dirty(pool, phone, fid):
    """Leave every kind of trace the script has to remove."""
    await pool.execute("UPDATE farmers SET lang = 'kn', consent_version = 'v1', consent_at = now() WHERE id = $1::uuid", fid)
    sid = await pool.fetchval("""INSERT INTO call_sessions (id, phone, farmer_id, kind, provider, state, data, version)
        VALUES (gen_random_uuid(), $1, $2::uuid, 'LISTING', 'exotel', 'LANG', '{}', 1) RETURNING id::text""", phone, fid)
    await pool.execute("INSERT INTO dtmf_events (session_id, event_id, state_before, digits, state_after) "
                       "VALUES ($1::uuid, 'e1', 'LANG', '1', 'CONSENT')", sid)
    await pool.execute("INSERT INTO consent_log (farmer_id, version, lang, session_id, digit) VALUES ($1::uuid, 'v1', 'kn', $2::uuid, '1')", fid, sid)
    await pool.execute("INSERT INTO triage_tickets (phone, farmer_id, reason, verbal_code) VALUES ($1, $2::uuid, 'HELP_KEY', '42')", phone, fid)
    await pool.execute("INSERT INTO call_jobs (phone, farmer_id, kind, payload, dedupe_key) VALUES ($1, $2::uuid, 'CALLBACK', '{}', $3)",
                       phone, fid, "cb:t:" + phone)
    r = cache.redis
    for k, v in [(f"sess:{phone}", "x"), (f"lock:call:{phone}", "x"), (f"miss:{phone}", "1"), (f"fail:{phone}", "2"),
                 (f"rl:cb:{phone}:10m", "3"), (f"rl:cb:{phone}:day", "3"), (f"unk:{phone}", "1"),
                 (f"callmap:exotel:CA-mine-{phone[-4:]}", phone), (f"callmap:exotel:CA-mine-{phone[-4:]}:job", "{}"),
                 ("callmap:exotel:CA-someone-else", "+919000000000")]:
        await r.set(k, v)


async def test_a_used_phone_becomes_a_first_time_farmer_and_the_cluster_is_recomputed(env):
    pool = env
    (a, fa), (b, fb) = await setup_farmers(2)
    await clustering.commit_listing(pool, session(a, fa, 15, 3000))
    await clustering.commit_listing(pool, session(b, fb, 10, 3100))                   # 25 q: READY
    cid = await pool.fetchval("SELECT id::text FROM clusters WHERE collection_point_id = $1::uuid", CP)
    assert await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid) == "READY"
    await dirty(pool, a, fa)

    out = await reset_caller.reset_phone(pool, a)
    assert out["listings_cleared"] == 1 and out["redis_keys"] == 9
    assert "lang=None, consent=None, district=KA-MANDYA" in out["state"]
    for table in ("call_sessions", "call_jobs", "triage_tickets"):
        assert await pool.fetchval(f"SELECT count(*) FROM {table} WHERE phone = $1", a) == 0
    assert await pool.fetchval("SELECT count(*) FROM consent_log WHERE farmer_id = $1::uuid", fa) == 0
    assert await pool.fetchval("SELECT count(*) FROM dtmf_events WHERE event_id = 'e1'") == 0
    assert await pool.fetchval("SELECT count(*) FROM listings WHERE farmer_id = $1::uuid", fa) == 0
    for k in (f"sess:{a}", f"lock:call:{a}", f"miss:{a}", f"fail:{a}", f"rl:cb:{a}:10m", f"rl:cb:{a}:day", f"unk:{a}",
              f"callmap:exotel:CA-mine-{a[-4:]}"):
        assert await cache.redis.get(k) is None, k
    assert await cache.redis.get("callmap:exotel:CA-someone-else") == "+919000000000"          # other people's calls untouched
    c = await pool.fetchrow("SELECT status, total_qtl, listing_count FROM clusters WHERE id = $1::uuid", cid)
    assert (c["status"], float(c["total_qtl"]), c["listing_count"]) == ("OPEN", 10.0, 1)         # 10 q left: no longer READY
    f = await pool.fetchrow("SELECT lang, consent_at, status FROM farmers WHERE id = $1::uuid", fa)
    assert f["lang"] is None and f["consent_at"] is None and f["status"] == "ACTIVE"
    await cache.redis.delete("callmap:exotel:CA-someone-else")


async def test_the_last_lot_in_a_cluster_removes_the_empty_cluster(env):
    pool = env
    (a, fa), = await setup_farmers(1)
    await clustering.commit_listing(pool, session(a, fa, 5, 3000))
    out = await reset_caller.reset_phone(pool, a)
    assert out["listings_cleared"] == 1
    assert await pool.fetchval("SELECT count(*) FROM clusters WHERE collection_point_id = $1::uuid", CP) == 0


async def test_keep_listings_leaves_them_and_a_running_auction_is_never_touched(env):
    pool = env
    (a, fa), (b, fb) = await setup_farmers(2)
    await clustering.commit_listing(pool, session(a, fa, 5, 3000))
    out = await reset_caller.reset_phone(pool, a, keep_listings=True)
    assert out["listings_cleared"] == 0 and await pool.fetchval("SELECT count(*) FROM listings WHERE farmer_id = $1::uuid", fa) == 1
    await clustering.commit_listing(pool, session(b, fb, 20, 3100))
    await pool.execute("UPDATE clusters SET status = 'BIDDING' WHERE collection_point_id = $1::uuid", CP)    # an auction is running
    out = await reset_caller.reset_phone(pool, b)
    assert out["listings_cleared"] == 0 and out["listings_kept"] == 1                                     # protected
    assert await pool.fetchval("SELECT status FROM clusters WHERE collection_point_id = $1::uuid", CP) == "BIDDING"
    assert (await pool.fetchrow("SELECT lang FROM farmers WHERE id = $1::uuid", fb))["lang"] is None        # but the caller state is reset
    await teardown5()


async def test_a_new_number_is_registered_and_targets_are_normalised(env):
    pool = env
    out = await reset_caller.reset_phone(pool, "+919000000042")
    row = await pool.fetchrow("SELECT lang, consent_at, district_code, status, fpo_id, collection_point_id "
                              "FROM farmers WHERE phone = '+919000000042'")
    assert out["registered_now"] and row["district_code"] == "KA-MANDYA" and row["lang"] is None and row["status"] == "ACTIVE"
    assert row["fpo_id"] and row["collection_point_id"]
    await pool.execute("DELETE FROM farmers WHERE phone = '+919000000042'")
    got = reset_caller.targets([" 098450-12345", "bad", "+91 98450 12345", '"9845012346"'], only=True)
    assert got == ["+919845012345", "+919845012346"]
