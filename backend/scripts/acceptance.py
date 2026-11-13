"""Acceptance checklist as a script (blueprint section 10, items 1-11 and 14). Owner: Darshan.

Drives the whole story through the REAL API and the phone-simulator WebSocket of a RUNNING backend, with real
Postgres/Valkey behind it, and prints PASS/FAIL per item. Items 12 (Exotel phone) and 13 (backup laptop) are manual.

  python backend/scripts/acceptance.py --reset            # wipes the trade data of the configured database first
  python backend/scripts/acceptance.py --reset --base http://localhost:8004

Run it against a throw-away setup, NOT while someone is rehearsing: it resets the database and Redis it points at.
Recommended (separate test database and Redis db 1, simulator only, so no real Exotel call can happen):
  DATABASE_URL=<.../annadata_test> REDIS_URL=redis://localhost:6379/1 TELEPHONY_PROVIDER=sim \
  SIM_RING_MIN=0.3 SIM_RING_MAX=0.6 SIM_HANGUP_DELAY=0.4 RL_CB_10M=500 RL_CB_DAY=5000 \
  python -m uvicorn app.main:app --port 8004      (from backend/), then run this script with the SAME env and --base.
Exit code 0 only if every automatic item passed. Item 14 is "run it twice": run it twice in a row (each --reset).
"""
import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402
import websockets  # noqa: E402

from app.config import settings  # noqa: E402

PHONES = [f"+91980000000{n}" for n in range(1, 9)]
PASSWORD = os.getenv("SEED_PASSWORD", "change-me")
PHONE_RE = re.compile(r"(?<![\w.])(\+?91)?[6-9]\d{9}(?![\w.])")     # a farmer phone number (not inside a UUID or a decimal)


class Report:
    def __init__(self):
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""), flush=True)
        return bool(ok)

    def summary(self) -> int:
        bad = [r for r in self.rows if not r[1]]
        print(f"\n{len(self.rows) - len(bad)}/{len(self.rows)} automatic checks passed" +
              ("" if not bad else "; FAILED: " + "; ".join(r[0] for r in bad)))
        print("MANUAL: item 12 (button phone through Exotel), item 13 (backup laptop offline), item 14 = run this twice")
        return 1 if bad else 0


class Api:
    def __init__(self, base: str):
        self.http, self.seen = httpx.AsyncClient(base_url=base, timeout=30), []

    async def call(self, method, path, token=None, scan=False, **kw):
        h = {**({"Authorization": f"Bearer {token}"} if token else {}), **kw.pop("headers", {})}
        r = await self.http.request(method, path, headers=h, **kw)
        if scan:
            self.seen.append((f"{method} {path}", r.text))              # buyer/agent responses are scanned for phones
        return r

    async def login(self, email, password=PASSWORD):
        r = await self.call("POST", "/api/auth/buyer/login", json={"email": email, "password": password})
        return r.json()["token"]


class Feed:
    """A dashboard WebSocket: keeps every event with its arrival time."""

    def __init__(self, base: str, token: str):
        self.url, self.events, self.task = base.replace("http", "ws") + f"/ws?token={token}&since=0", [], None

    async def start(self):
        self.ws = await websockets.connect(self.url)
        self.task = asyncio.create_task(self._pump())

    async def _pump(self):
        try:
            async for raw in self.ws:
                self.events.append((time.time(), json.loads(raw)))
        except Exception:
            pass

    async def wait(self, pred, timeout=5.0, after=0.0):
        end = time.time() + timeout
        while time.time() < end:
            for t, e in self.events:
                if t >= after and pred(e):
                    return t, e
            await asyncio.sleep(0.05)
        return None, None

    async def stop(self):
        self.task.cancel()
        await self.ws.close()


class Phone:
    """A simulated handset on the C6 WebSocket."""

    def __init__(self, base: str, phone: str):
        self.url, self.phone, self.seq, self.ws = base.replace("http", "ws") + f"/tel/sim/ws?phone={quote(phone)}", phone, 0, None

    async def connect(self):
        self.ws = await websockets.connect(self.url)

    async def recv(self, timeout=25):
        return json.loads(await asyncio.wait_for(self.ws.recv(), timeout))

    async def send(self, **m):
        await self.ws.send(json.dumps(m))

    async def press(self, cid, keys: str, play, bounce=False):
        if play["max_digits"] and len(keys) < play["max_digits"] and play["finish_on_key"]:
            keys += play["finish_on_key"]
        for ch in keys:
            await asyncio.sleep(0.2)
            ts = int(time.time() * 1000)
            self.seq += 1
            await self.send(t="digit", call_id=cid, d=ch, ts_ms=ts, seq=self.seq)
            if bounce:
                self.seq += 1
                await self.send(t="digit", call_id=cid, d=ch, ts_ms=ts + random.randint(30, 60), seq=self.seq)

    async def call(self, answers: dict, *, incoming=False, drop_after=None, bounce=False, on_state=None, ring_timeout=25):
        """Run one call. Returns {"states": [...], "info": reason|None, "final_at": time of the FINAL key, "seconds": n}."""
        t0, out = time.time(), {"states": [], "info": None, "final_at": None}
        if not incoming:
            await self.send(t="missed_call")
        while True:
            m = await self.recv(ring_timeout)
            if m["t"] == "ring":
                break
            if m["t"] == "info" and not incoming:
                out["info"] = m["reason"]
                return out
        cid = m["call_id"]
        await self.send(t="answer", call_id=cid)
        while True:
            m = await self.recv()
            if m["t"] == "hangup":
                break
            if m["t"] != "play":
                continue
            st = m["state"]
            out["states"].append(st)
            if on_state:
                await on_state(st)
            if st == drop_after:
                await self.send(t="hangup", call_id=cid)
                break
            if m["max_digits"] == 0:
                continue                                                # closing prompt: the server hangs up
            if st == "FINAL":
                out["final_at"] = time.time()
            await self.press(cid, answers.get(st, "9"), m, bounce)
        out["seconds"] = time.time() - t0
        return out


async def main(base: str, reset: bool) -> int:
    rep = Report()
    if reset:
        import demo_reset
        await demo_reset.main(empty=True, keep_farmers=False)
        await asyncio.sleep(1.5)
    db = await asyncpg.connect(settings.database_url)
    rds = aioredis.from_url(settings.redis_url, decode_responses=True)
    api = Api(base)
    fresh = lambda p: rds.delete(f"miss:{p}")                           # skip the 20 s duplicate window between calls
    print(f"acceptance run against {base}, database {settings.database_url.rsplit('/', 1)[1]}\n")

    admin, b1, b2 = await api.login("admin@demo.test"), await api.login("buyer1@demo.test"), await api.login("buyer2@demo.test")
    ag = (await api.call("POST", "/api/auth/agent/login", json={"phone": "+919800000099", "pin": os.getenv("AGENT_PIN", "1234")})).json()["token"]
    adm_feed, b1_feed = Feed(base, admin), Feed(base, b1)
    await adm_feed.start(), await b1_feed.start()
    phones = [Phone(base, p) for p in PHONES]
    for p in phones:
        await p.connect()
    F = {i + 1: p for i, p in enumerate(phones)}
    base_ans = {"LANG": "1", "CONSENT": "1", "CROP": "1", "QTY": "5", "QTY_CONFIRM": "1", "PRICE": "3600", "FINAL": "1"}

    async def listing(n, **extra):
        await fresh(PHONES[n - 1])
        return await F[n].call({**base_ans, **extra.pop("answers", {})}, **extra)

    async def stored(n):
        return await db.fetchrow("""SELECT l.qty_qtl, l.ask_price, l.guardrail FROM listings l JOIN farmers f ON f.id = l.farmer_id
                                    WHERE f.phone = $1 AND l.crop_code = 'ragi'""", PHONES[n - 1])

    # --- 1 and 8: callback, bounce-proof numbers, dashboard in under 1 s -------------------------------------
    print("1 / 8  missed call -> listing (with key bounce)")
    t_start = time.time()
    r1 = await listing(1, bounce=True)
    row = await stored(1)
    rep.check("1  callback and listing confirmed in under 90 s", r1["states"][-1] == "DONE" and time.time() - t_start < 90,
              f"{time.time() - t_start:.0f}s, states {len(r1['states'])}")
    t_evt, _ = await adm_feed.wait(lambda e: e.get("type") == "cluster.updated", 3, after=r1["final_at"] or 0)
    rep.check("1  listing visible on the dashboard in under 1 s", bool(t_evt and r1["final_at"] and t_evt - r1["final_at"] < 1.0),
              f"{(t_evt - r1['final_at']) * 1000:.0f} ms" if t_evt and r1["final_at"] else "no event")
    rep.check("8  with the bounce switch on, the stored quantity is still 5 (not 55)", row and float(row["qty_qtl"]) == 5,
              str(dict(row)) if row else "no listing")
    dtmf = (await api.call("GET", "/api/ops/dtmf?limit=100", admin)).json()["events"]
    rep.check("8  the ops feed shows BOUNCE rows", any(e["dropped_reason"] == "BOUNCE" for e in dtmf),
              f"{sum(e['dropped_reason'] == 'BOUNCE' for e in dtmf)} rows")

    # --- 2: hang up at PRICE, call again, resume ------------------------------------------------------------
    print("2  hang up mid-call, call again")
    await listing(2, drop_after="PRICE")
    r2 = await listing(2)
    rep.check("2  the next call resumes at PRICE", r2["states"][:1] == ["PRICE"] and r2["states"][-1] == "DONE", str(r2["states"][:3]))

    # --- 9: flush Redis mid-call ----------------------------------------------------------------------------
    print("9  flush Redis mid-call")
    flushed = []

    async def flush_at_price(st):
        if st == "PRICE" and not flushed:
            flushed.append((await api.call("POST", "/api/ops/chaos/flush-redis", admin)).status_code)
    r3 = await listing(3, on_state=flush_at_price)
    rep.check("9  the call continues after Redis is flushed", flushed == [200] and r3["states"][-1] == "DONE" and bool(await stored(3)),
              f"flush HTTP {flushed}")

    # --- 3: price guardrail ---------------------------------------------------------------------------------
    print("3  price below the floor")
    r4 = await listing(4, answers={"PRICE": "3000", "GUARD": "1"})
    r5 = await listing(5, answers={"PRICE": "3000", "GUARD": "2"})
    s4, s5 = await stored(4), await stored(5)
    rep.check("3  warning shown when the price is below the floor", "GUARD" in r4["states"] and "GUARD" in r5["states"])
    rep.check("3  'raise' stores the floor price", s4 and float(s4["ask_price"]) == 3430 and s4["guardrail"] == "RAISED", str(dict(s4)) if s4 else "")
    rep.check("3  'keep' stores the farmer's own price", s5 and float(s5["ask_price"]) == 3000 and s5["guardrail"] == "KEPT_BELOW", str(dict(s5)) if s5 else "")

    # --- 4: READY and exactly one verification task ---------------------------------------------------------
    print("4  cluster reaches 20 quintals")
    clusters = (await api.call("GET", "/api/clusters", b1, scan=True)).json()["clusters"]
    ragi = next((c for c in clusters if c["crop_code"] == "ragi"), None)
    cid = ragi["id"] if ragi else ""
    tasks = [e for _, e in adm_feed.events if e.get("type") == "task.created" and e["payload"].get("ref_id") == cid]
    rep.check("4  the 20-quintal listing turns the cluster READY", bool(ragi) and ragi["status"] == "READY" and ragi["total_qtl"] == 25,
              f"{ragi['status']} {ragi['total_qtl']} q" if ragi else "no cluster")
    rep.check("4  exactly one verification task was created", len(tasks) == 1, f"{len(tasks)} task events")

    # --- 10: three failed calls -> one helper ticket --------------------------------------------------------
    print("10  three failed calls")
    for _ in range(3):
        await listing(6, answers={"LANG": "9"})                         # never a valid key
    tickets = await db.fetch("SELECT verbal_code, reason FROM triage_tickets WHERE phone = $1", PHONES[5])
    rep.check("10  three failed calls open exactly one helper ticket", len(tickets) == 1 and tickets[0]["reason"] == "IVR_FAIL_3",
              f"{len(tickets)} ticket(s)")
    tk = (await api.call("GET", "/api/agent/tasks", ag, scan=True)).json()["tickets"]
    code = None
    if tk:
        await api.call("POST", f"/api/agent/triage/{tk[0]['id']}/claim", ag, scan=True)
        code = (await api.call("POST", f"/api/agent/triage/{tk[0]['id']}/bridge", ag, scan=True)).json().get("verbal_code")
    rep.check("10  the agent sees the 2-digit code stored for the IVR to speak", bool(tickets) and code == tickets[0]["verbal_code"] and bool(code),
              f"code {code}")

    # --- 5: verification at the venue -----------------------------------------------------------------------
    print("5  agent verification")
    cp = ragi["collection_point"] if ragi else {"lat": 0, "lon": 0}

    def form(lat, lon):
        return {"grade": "A", "lat": str(lat), "lon": str(lon), "accuracy_m": "10",
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())}
    jpg = {"photo": ("s.jpg", b"\xff\xd8\xff acceptance", "image/jpeg")}
    far = await api.call("POST", f"/api/agent/clusters/{cid}/verification", ag, scan=True, data=form(cp["lat"] + 0.3, cp["lon"]), files=jpg)
    ok = await api.call("POST", f"/api/agent/clusters/{cid}/verification", ag, scan=True, data=form(cp["lat"], cp["lon"]), files=jpg)
    rep.check("5  a faked far location gets TOO_FAR", far.status_code == 422 and far.json().get("error") == "TOO_FAR")
    rep.check("5  verification at the venue succeeds and opens bidding", ok.status_code == 201 and ok.json().get("status") == "BIDDING", ok.text[:80])

    # --- 6: bidding -------------------------------------------------------------------------------------------
    print("6  bidding")
    url, key = f"/api/clusters/{cid}/bids", "dbl-" + uuid.uuid4().hex[:6]
    a = await api.call("POST", url, b1, scan=True, headers={"Idempotency-Key": key}, json={"price_per_qtl": 3200, "min_qty_qtl": 25})
    b = await api.call("POST", url, b1, scan=True, headers={"Idempotency-Key": key}, json={"price_per_qtl": 3200, "min_qty_qtl": 25})
    rep.check("6  a double-click records one bid", a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"])
    t_before = time.time()
    await api.call("POST", url, b2, scan=True, headers={"Idempotency-Key": uuid.uuid4().hex}, json={"price_per_qtl": 3210, "min_qty_qtl": 25})
    t_evt, ev = await b1_feed.wait(lambda e: e.get("type") == "cluster.updated" and e["payload"].get("id") == cid
                                   and (e["payload"].get("best_bid") or {}).get("price_per_qtl") == 3210, 3, after=t_before)
    rep.check("6  the outbid buyer's screen updates live", bool(ev) and ev["payload"]["best_bid"]["mine"] is False,
              f"{(t_evt - t_before) * 1000:.0f} ms" if t_evt else "no event")

    # --- 7: auction close -> offer calls -> deal only if accepted quantity >= minimum ----------------------------
    print("7  confirmation calls")

    async def offers(accept_up_to=4):
        async def one(n):
            ans = {"OFFER": "1" if n <= accept_up_to else "2", "OFFER_CONFIRM": "1"}
            return await F[n].call(ans, incoming=True, ring_timeout=30)
        return await asyncio.gather(*[one(n) for n in range(1, 6)])

    await api.call("POST", f"/api/admin/clusters/{cid}/close-auction", admin)
    await offers()
    await asyncio.sleep(1.5)
    deal_a = await db.fetchval("SELECT count(*) FROM deals WHERE cluster_id = $1::uuid", cid)
    st_a = await db.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cid)
    rep.check("7  accepted 20 q < the buyer's minimum of 25: no deal, bidding reopens", deal_a == 0 and st_a == "BIDDING", f"deals {deal_a}, cluster {st_a}")
    await api.call("POST", url, b1, scan=True, headers={"Idempotency-Key": uuid.uuid4().hex}, json={"price_per_qtl": 3220, "min_qty_qtl": 20})
    await api.call("POST", f"/api/admin/clusters/{cid}/close-auction", admin)
    await offers()
    await asyncio.sleep(1.5)
    deal = await db.fetchrow("SELECT qty_qtl, price_per_qtl FROM deals WHERE cluster_id = $1::uuid", cid)
    rep.check("7  accepted 20 q >= minimum 20: a deal of exactly the accepted quantity",
              bool(deal) and float(deal["qty_qtl"]) == 20 and float(deal["price_per_qtl"]) == 3220, str(dict(deal)) if deal else "no deal")

    # --- 11: no phone numbers in buyer/agent responses --------------------------------------------------------
    leaks = [(p, m.group(0)) for p, body in api.seen for m in [PHONE_RE.search(body)] if m]
    rep.check("11 no farmer phone number in any buyer or agent response", not leaks, f"{len(api.seen)} responses scanned" + (f"; LEAK in {leaks[0][0]}" if leaks else ""))

    for f in (adm_feed, b1_feed):
        await f.stop()
    for p in phones:
        await p.ws.close()
    await db.close()
    await rds.aclose()
    return rep.summary()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--reset", action="store_true", help="wipe the trade data of the configured database first")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.base, a.reset)))
