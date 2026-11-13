"""D7: Exotel adapter against a mocked Exotel API (no network). Real Postgres + Valkey, real queue and engine."""
import itertools
import json
import uuid

import httpx
import pytest

from app import cache, db
from app.config import settings
from app.engine.deps import PgDeps
from app.main import app
from app.services import bidding, jobs
from app.telephony import base, exotel, sim
from test_d4 import setup_farmers
from test_jobs import full_teardown, make_round
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")

SECRET = "s3cret-" + "x" * 24
OVERRIDES = {"webhook_secret": SECRET, "exotel_sid": "annadata1", "exotel_api_key": "key1", "exotel_api_token": "tok1",
             "exophone": "08040000000", "exotel_app_id": "12345", "public_base_url": "https://demo.example",
             "provider": "exotel"}


class FakeExotel:
    """Records connect.json requests; hands out call sids CA1, CA2, ..."""

    def __init__(self):
        self.requests, self.fail, self._n = [], False, itertools.count(1)
        self.tag = uuid.uuid4().hex[:6]                    # real CallSids are unique; so are ours between runs

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"Call": {"Sid": f"CA{self.tag}{next(self._n)}"}})


@pytest.fixture
async def env():
    pool = await db.connect()
    await cache.connect()
    await full_teardown()
    saved = {k: getattr(settings, k) for k in OVERRIDES}
    for k, v in OVERRIDES.items():
        object.__setattr__(settings, k, v)
    base.set_provider(None)
    app.state.deps = PgDeps(pool)
    fake = FakeExotel()
    orig = exotel._client
    exotel._client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield pool, fake, http
    exotel._client = orig
    for k, v in saved.items():
        object.__setattr__(settings, k, v)
    await full_teardown()
    await cache.close()
    await db.close()


def url(path):
    return f"/tel/exotel/{SECRET}/{path}"


def exo_form(phone):                       # how Exotel writes an Indian number: 0 + ten digits
    return "0" + phone[3:]


async def keys(pool, phone):
    return await pool.fetchrow("SELECT id::text, status, attempts, last_error, provider_call_id FROM call_jobs "
                               "WHERE phone = $1 ORDER BY created_at DESC LIMIT 1", phone)


async def start_callback(pool, http, phone, sid="M1"):
    r = await http.post(url("missed"), data={"From": exo_form(phone), "CallSid": sid, "To": "08040000000",
                                             "Status": "missed-call"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    await pool.execute("UPDATE call_jobs SET run_at = now() WHERE phone = $1", phone)
    await jobs.tick()
    return await keys(pool, phone)


async def gather(http, sid, step, expect=200):
    r = await http.get(url("gather"), params={"CallSid": sid, "step": step, "CallFrom": "08040000000"})
    assert r.status_code == expect, r.text
    return r.json()


async def digits(http, sid, step, d=None):
    params = {"CallSid": sid, "step": step}
    if d is not None:
        params["digits"] = f'"{d}"'                                  # Exotel wraps digits in literal quotes
    return await http.get(url("digits"), params=params)


def test_number_and_digit_cleaning():
    assert exotel.normalise("08123456789") == "+918123456789"
    assert exotel.normalise("918123456789") == "+918123456789"
    assert exotel.normalise("+91 81234 56789") == "+918123456789"
    assert exotel.normalise("8123456789") == "+918123456789"
    assert exotel.normalise("12345") is None and exotel.normalise("") is None
    assert exotel.strip_digits('"17"') == "17" and exotel.strip_digits("") == "" and exotel.strip_digits(' "1" ') == "1"


async def test_wrong_secret_and_unknown_calls_are_refused(env):
    pool, fake, http = env
    for path in ("missed", "gather", "digits", "status"):
        r = await http.get(f"/tel/exotel/wrong/{path}", params={"CallSid": "x", "step": 1})
        assert r.status_code == 403
    assert (await http.get(url("gather"), params={"CallSid": "CA-not-ours", "step": 1})).status_code == 403
    assert (await digits(http, "CA-not-ours", 1, "1")).status_code == 403
    assert (await http.post(url("status"), data={"CallSid": "CA-not-ours", "Status": "completed"})).status_code == 403
    object.__setattr__(settings, "webhook_secret", "")                  # an unset secret must not open the door
    assert (await http.get("/tel/exotel//gather", params={"CallSid": "x"})).status_code in (403, 404)


async def test_missed_call_queues_one_callback_and_unknown_numbers_only_once(env):
    pool, fake, http = env
    (phone, _), = await setup_farmers(1)
    for sid in ("M1", "M2"):                                          # second one is inside the 20 s dedupe window
        await http.post(url("missed"), data={"From": exo_form(phone), "CallSid": sid})
    assert await pool.fetchval("SELECT count(*) FROM call_jobs WHERE phone = $1 AND kind = 'CALLBACK'", phone) == 1
    stranger = "+917799123456"
    await cache.redis.delete(f"unk:{stranger}", f"miss:{stranger}")
    for sid in ("U1", "U2"):
        await cache.redis.delete(f"miss:{stranger}")
        await http.post(url("missed"), data={"From": exo_form(stranger), "CallSid": sid})
    assert await pool.fetchval("SELECT count(*) FROM call_jobs WHERE phone = $1", stranger) == 1
    assert (await http.post(url("missed"), data={"From": "garbage", "CallSid": "G"})).json() == {"ok": True}


async def test_callback_sends_the_connect_request_exotel_expects(env):
    pool, fake, http = env
    (phone, _), = await setup_farmers(1)
    job = await start_callback(pool, http, phone)
    req = fake.requests[0]
    assert req.method == "POST" and str(req.url) == "https://api.exotel.com/v1/Accounts/annadata1/Calls/connect.json"
    assert req.headers["authorization"].startswith("Basic ")
    form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
    from urllib.parse import unquote_plus
    form = {k: unquote_plus(v) for k, v in form.items()}
    assert form["From"] == phone and form["CallerId"] == "08040000000" and form["CallType"] == "trans"
    assert form["Url"] == "http://my.exotel.com/annadata1/exoml/start_voice/12345"
    assert form["StatusCallback"] == f"https://demo.example/tel/exotel/{SECRET}/status"
    assert form["TimeLimit"] == "240" and form["TimeOut"] == "30" and form["CustomField"] == job["id"]
    assert job["status"] == "DIALING" and job["provider_call_id"] == f"CA{fake.tag}1"
    assert await cache.redis.get(f"callmap:exotel:CA{fake.tag}1") == phone


async def test_full_listing_over_exotel_from_missed_call_to_done(env):
    pool, fake, http = env
    (phone, _), = await setup_farmers(1)
    job = await start_callback(pool, http, phone)
    sid = job["provider_call_id"]

    g = await gather(http, sid, 1)                                      # first prompt: language menu
    assert g["gather_prompt"]["audio_url"].startswith("https://demo.example/audio/mix/")
    assert g["max_input_digits"] == 1 and g["input_timeout"] == 6, g
    assert (await keys(pool, phone))["status"] == "IN_CALL" and await cache.redis.exists(f"lock:call:{phone}")

    # (key pressed, prompt that follows): language -> consent -> crop -> quantity -> readback -> price -> final
    for step, d, maxd, fin in [(1, "1", 1, None), (2, "1", 1, None), (3, "1", 2, "#"), (4, "17", 1, None),
                               (5, "1", 5, "#"), (6, "3600", 1, None)]:
        assert (await digits(http, sid, step, d)).status_code == 200
        g = await gather(http, sid, step + 1)
        assert g["max_input_digits"] == maxd and (fin is None or g["finish_on_key"] == fin)
    assert (await digits(http, sid, 7, "1")).status_code == 200         # FINAL: the only commit
    assert (await digits(http, sid, 7, "1")).status_code == 200         # Exotel retries the Passthru: same answer, no 2nd listing
    last = await gather(http, sid, 8)
    assert last["input_timeout"] == 1                                    # closing prompt plays once
    assert (await digits(http, sid, 8)).status_code == 404               # no key -> hang-up branch
    q = await pool.fetch("""SELECT l.qty_qtl, l.ask_price FROM listings l JOIN farmers f ON f.id = l.farmer_id
                            WHERE f.phone = $1""", phone)
    assert len(q) == 1 and float(q[0]["qty_qtl"]) == 17 and float(q[0]["ask_price"]) == 3600
    assert (await pool.fetchval("SELECT provider FROM call_sessions WHERE phone = $1", phone)) == "exotel"

    r = await http.post(url("status"), data={"CallSid": sid, "Status": "completed", "CustomField": job["id"]})
    assert r.status_code == 200
    assert (await keys(pool, phone))["status"] == "DONE" and not await cache.redis.exists(f"lock:call:{phone}")


async def test_bad_key_replays_the_prompt_with_the_error_clip(env):
    pool, fake, http = env
    (phone, _), = await setup_farmers(1)
    sid = (await start_callback(pool, http, phone))["provider_call_id"]
    first = await gather(http, sid, 1)
    assert (await digits(http, sid, 1, "9")).status_code == 200          # invalid on the language menu
    again = await gather(http, sid, 2)
    clips = json.loads(await cache.redis.get(f"exo:act:{sid}"))["clips"]            # (no audio files here: URLs are all the beep)
    assert clips[0] == "bad_input" and again["input_timeout"] == first["input_timeout"]
    for step in (2, 3):                                                  # third miss ends the call
        await digits(http, sid, step, "9")
        await gather(http, sid, step + 1)
    assert (await digits(http, sid, 4)).status_code == 404


async def test_unanswered_call_is_retried_and_an_unreachable_exotel_is_too(env):
    pool, fake, http = env
    (phone, _), = await setup_farmers(1)
    job = await start_callback(pool, http, phone)
    r = await http.post(url("status"), data={"CallSid": job["provider_call_id"], "Status": "no-answer",
                                             "CustomField": job["id"]})
    j = await keys(pool, phone)
    assert r.status_code == 200 and j["status"] == "QUEUED" and j["last_error"] == "NO_ANSWER" and j["attempts"] == 1
    fake.fail = True                                                     # Exotel down: the job waits, nothing is lost
    await pool.execute("UPDATE call_jobs SET run_at = now() WHERE phone = $1", phone)
    await jobs.tick()
    j = await keys(pool, phone)
    assert j["status"] == "QUEUED" and j["last_error"] == "NO_LINE" and j["attempts"] == 2


async def test_second_call_to_a_busy_farmer_is_turned_away(env):
    pool, fake, http = env
    (phone, _), = await setup_farmers(1)
    sid = (await start_callback(pool, http, phone))["provider_call_id"]
    await cache.redis.set(f"lock:call:{phone}", "another-call", px=60_000)
    g = await gather(http, sid, 1)
    assert g["input_timeout"] == 1
    assert (await digits(http, sid, 1, "1")).status_code == 404


async def test_missing_exotel_settings_fail_safely(env):
    pool, fake, http = env
    object.__setattr__(settings, "exotel_app_id", "")
    (phone, _), = await setup_farmers(1)
    job = await start_callback(pool, http, phone)
    assert job["status"] == "QUEUED" and job["last_error"] == "NO_LINE" and fake.requests == []


async def test_farmers_bid_offer_call_goes_over_exotel_and_settles_the_round(env):
    pool, fake, http = env
    farmers, cid, bid = await make_round(pool, [10, 10], min_qty=10)
    await jobs.tick()                                                    # both phones are real numbers -> Exotel
    assert len(fake.requests) == 2
    sids = {p: (await keys(pool, p))["provider_call_id"] for p, _ in farmers}
    (p1, _), (p2, _) = farmers

    g = await gather(http, sids[p1], 1)                                  # offer is read out
    assert g["max_input_digits"] == 1 and g["input_timeout"] == 8
    await digits(http, sids[p1], 1, "1")
    await gather(http, sids[p1], 2)                                      # "to confirm press one"
    assert await pool.fetchval("SELECT count(*) FROM bid_responses WHERE bid_id = $1::uuid AND response <> 'PENDING'", bid) == 0
    await digits(http, sids[p1], 2, "1")
    assert (await gather(http, sids[p1], 3))["input_timeout"] == 1
    assert (await digits(http, sids[p1], 3)).status_code == 404
    await http.post(url("status"), data={"CallSid": sids[p1], "Status": "completed"})

    await gather(http, sids[p2], 1)
    await digits(http, sids[p2], 1, "2")                                 # second farmer rejects
    await http.post(url("status"), data={"CallSid": sids[p2], "Status": "completed"})

    deal = await pool.fetchrow("SELECT qty_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
    assert float(deal["qty_qtl"]) == 10
    assert {(await keys(pool, p))["status"] for p, _ in farmers} == {"DONE"}


async def test_simulator_farmers_still_ring_on_the_browser_while_exotel_is_the_provider(env):
    pool, fake, http = env
    assert base.get_provider("+919800000099") is exotel
    sim.LINES["+919800000099"] = {"ws": None, "call_id": None, "incoming": None}
    try:
        assert base.get_provider("+919800000099") is sim
    finally:
        sim.LINES.pop("+919800000099", None)
