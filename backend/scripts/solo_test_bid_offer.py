"""Solo end-to-end test of the farmer bid-offer call: one command, one real phone ring. Owner: Darshan.

  python backend/scripts/solo_test_bid_offer.py --dry-run            # show the plan, change nothing
  python backend/scripts/solo_test_bid_offer.py                      # the real run
  python backend/scripts/solo_test_bid_offer.py --phone +91XXXXXXXXXX --price 3850

What it does, using the same API and code paths as the real people:
  1. picks the real phone (--phone, else the real farmer who listed most recently, else the first TEAM_PHONES entry) and
     refuses anything that is not in TEAM_PHONES or that is a seeded demo number;
  2. makes sure that farmer has a 5-quintal ragi lot in a ragi cluster at the yard (registers/lists if needed) and, if the cluster
     is still OPEN, tops it up to 20 quintals with simulator-farmer lots;
  3. verifies the cluster as the FPO agent (the real verification endpoint, at the yard's own coordinates) -> BIDDING;
  4. places the winning bid as buyer1@demo.test (default 3850 Rs/qtl, minimum quantity = the whole cluster, so the real farmer's
     "accept" decides whether a deal forms);
  5. pre-empts calls to the simulator farmers (never dialed) and records their ACCEPT, closes the auction -> CONFIRMING;
  6. the RUNNING SERVER's job worker then rings the real phone through Exotel. This script does not place the call itself
     (that would ring twice); it watches the job and prints Exotel's answer (a call id, or the reason it was refused).
Then you answer: press 1 (accept), then 1 again to confirm. The round settles and the buyer screen shows the deal.
Needs the backend running with TELEPHONY_PROVIDER=exotel, SEED_PASSWORD in .env. Runs against the dev database.
"""
import argparse
import asyncio
import os
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402

import close_for_demo  # noqa: E402
from app import cache, db  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import clustering  # noqa: E402

SIM = close_for_demo.SIMULATOR_PHONES
mask = close_for_demo.mask


def to_e164(raw: str) -> str:
    return "+91" + re.sub(r"\D", "", raw)[-10:]


class Stop(Exception):
    pass


async def pick_phone(pool, arg: str | None) -> str:
    if arg:
        phone = to_e164(arg)
    else:
        row = await pool.fetchrow("""SELECT f.phone FROM listings l JOIN farmers f ON f.id = l.farmer_id
                                     WHERE f.phone NOT LIKE '+91980000%' ORDER BY l.created_at DESC LIMIT 1""")
        if row:
            phone = row["phone"]
        else:
            first = next(iter(re.split(r"[,;\s]+", os.getenv("TEAM_PHONES", "").strip())), "")
            if not first:
                raise Stop("No real phone known: give --phone or set TEAM_PHONES in .env.")
            phone = to_e164(first)
    if phone[-10:].startswith("980000"):
        raise Stop(f"{mask(phone)} is a seeded demo number: it is never dialed. Use your own phone.")
    if settings.team_phones and phone[-10:] not in settings.team_phones:
        raise Stop(f"{mask(phone)} is not in TEAM_PHONES, so the server would refuse to dial it.")
    return phone


async def ensure_farmer(pool, phone: str) -> str:
    row = await pool.fetchrow("SELECT id::text FROM farmers WHERE phone = $1", phone)
    if row:
        return row["id"]
    cp = await pool.fetchrow("""SELECT id, fpo_id, district_code, ST_X(geog::geometry) AS lon, ST_Y(geog::geometry) AS lat
                                FROM collection_points ORDER BY name LIMIT 1""")
    if not cp:
        raise Stop("No pickup point in the database: run a seed first.")
    return await pool.fetchval("""INSERT INTO farmers (phone, name, fpo_id, village, district_code, geog, collection_point_id)
        VALUES ($1, 'Team Phone', $2, 'Keregodu', $3, ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography, $6) RETURNING id::text""",
                               phone, cp["fpo_id"], cp["district_code"], cp["lon"], cp["lat"], cp["id"])


async def commit_lot(pool, phone: str, farmer_id: str, qty: int, price: int) -> None:
    await clustering.commit_listing(pool, {
        "id": str(uuid.uuid4()), "phone": phone, "farmer_id": farmer_id, "kind": "LISTING", "provider": "sim",
        "call_id": "solo-" + uuid.uuid4().hex[:6], "state": "DONE", "version": 1,
        "data": {"crop": "ragi", "qty": qty, "price": price}})


async def my_cluster(pool, farmer_id: str):
    return await pool.fetchrow("""SELECT cl.id::text AS id, cl.code, cl.status, cl.total_qtl, cl.collection_point_id
                                  FROM listings l JOIN clusters cl ON cl.id = l.cluster_id
                                  WHERE l.farmer_id = $1::uuid AND l.crop_code = 'ragi'
                                  AND l.status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED')""", farmer_id)


async def run(pool, http, phone: str, price: int, poll_s: float = 30.0, say=print) -> dict:
    farmer_id = await ensure_farmer(pool, phone)
    cl = await my_cluster(pool, farmer_id)
    if cl and cl["status"] in ("NO_BID", "FAILED"):                          # an auction that ended unsold strands its lots
        await pool.execute("""UPDATE listings SET status = 'WITHDRAWN' WHERE farmer_id = $1::uuid AND crop_code = 'ragi'
                              AND cluster_id = $2::uuid AND status IN ('PENDING_CONFIRM','ACTIVE')""", farmer_id, cl["id"])
        say(f"  your lot was stranded in cluster #{cl['code']} ({cl['status']}): withdrawn, listing a fresh one")
        cl = None
    if not cl:
        await commit_lot(pool, phone, farmer_id, 5, 3600)
        cl = await my_cluster(pool, farmer_id)
        say(f"  listed 5 q of ragi for {mask(phone)}")
    if cl["status"] not in ("OPEN", "READY", "BIDDING"):
        raise Stop(f"Your ragi lot is in cluster #{cl['code']} which is {cl['status']}: pick another phone or run demo_reset.py.")

    if cl["status"] == "OPEN":                                               # top up to 20 q with simulator lots
        for i, sim in enumerate(sorted(SIM)):
            total = float(await pool.fetchval("SELECT total_qtl FROM clusters WHERE id = $1::uuid", cl["id"]))
            if total >= 20:
                break
            f = await pool.fetchrow("""SELECT id::text FROM farmers WHERE phone = $1 AND collection_point_id = $2
                AND NOT EXISTS (SELECT 1 FROM listings l WHERE l.farmer_id = farmers.id AND l.crop_code = 'ragi'
                                AND l.status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED'))""", sim, cl["collection_point_id"])
            if f:
                await commit_lot(pool, sim, f["id"], 5, 3550 + 10 * i)
        cl = await my_cluster(pool, farmer_id)
    say(f"  cluster #{cl['code']} ({cl['id']}): {cl['status']}, {float(cl['total_qtl']):g} q")

    if cl["status"] == "READY":                                              # step 3: the agent verifies it
        yard = await pool.fetchrow("""SELECT ST_Y(cp.geog::geometry) AS lat, ST_X(cp.geog::geometry) AS lon
                                      FROM collection_points cp WHERE cp.id = $1""", cl["collection_point_id"])
        ag = await http.post("/api/auth/agent/login", json={"phone": "+919800000099", "pin": os.getenv("AGENT_PIN", "1234")})
        if ag.status_code != 200:
            raise Stop(f"Agent login failed ({ag.status_code}).")
        r = await http.post(f"/api/agent/clusters/{cl['id']}/verification", headers={"Authorization": "Bearer " + ag.json()["token"]},
                            data={"grade": "A", "lat": str(yard["lat"]), "lon": str(yard["lon"]), "accuracy_m": "10",
                                  "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())},
                            files={"photo": ("solo.jpg", b"\xff\xd8\xff solo test", "image/jpeg")})
        if r.status_code != 201:
            raise Stop(f"Verification refused: {r.text[:120]}")
        say("  verified by the FPO agent -> BIDDING")

    # step 4: the winning bid
    c = await pool.fetchrow("""SELECT cl.total_qtl, cl.min_ask, b.price_per_qtl AS best FROM clusters cl
                               LEFT JOIN bids b ON b.id = cl.best_bid_id WHERE cl.id = $1::uuid""", cl["id"])
    bid_price = max(price, int(c["min_ask"] or 0), int(c["best"] + 10) if c["best"] is not None else 0)
    min_qty = float(c["total_qtl"])
    tok = await http.post("/api/auth/buyer/login", json={"email": "buyer1@demo.test", "password": os.getenv("SEED_PASSWORD", "")})
    if tok.status_code != 200:
        raise Stop(f"Buyer login failed ({tok.status_code}): is SEED_PASSWORD the one the database was seeded with?")
    bh = {"Authorization": "Bearer " + tok.json()["token"]}
    b = await http.post(f"/api/clusters/{cl['id']}/bids", headers={**bh, "Idempotency-Key": uuid.uuid4().hex},
                        json={"price_per_qtl": bid_price, "min_qty_qtl": min_qty})
    if b.status_code not in (200, 201):
        raise Stop(f"Bid refused: {b.text[:120]}")
    say(f"  winning bid: Rs {bid_price}/qtl for at least {min_qty:g} q by buyer1@demo.test")

    # steps 5 and 6: simulator farmers answer for themselves, the auction closes, the server rings the real phone
    async def closer(cid):
        adm = await http.post("/api/auth/buyer/login", json={"email": "admin@demo.test", "password": os.getenv("SEED_PASSWORD", "")})
        r = await http.post(f"/api/admin/clusters/{cid}/close-auction", headers={"Authorization": "Bearer " + adm.json()["token"]})
        say(f"  close-auction -> HTTP {r.status_code} {r.text[:60]}")
    out = await close_for_demo.close_with_simulated_farmers(pool, cl["id"], closer, sim_phones=SIM, accept=True)
    if "error" in out:
        raise Stop(out["error"])
    say(f"  {out['simulated']} simulator lot(s) ({out['sim_qtl']:g} q) accepted without any call; "
        f"waiting for the real phone(s): {', '.join(mask(p) for p in out['real'])}")

    job, end = None, time.time() + poll_s
    while True:
        job = await pool.fetchrow("""SELECT status, attempts, last_error, provider_call_id FROM call_jobs
                                     WHERE phone = $1 AND payload->>'bid_id' = $2""", phone, out["bid"])
        if poll_s == 0 or (job and (job["provider_call_id"] or job["status"] in ("FAILED", "CANCELLED", "DONE"))) or time.time() > end:
            break
        await asyncio.sleep(1)
    return {"cluster_id": cl["id"], "cluster_code": cl["code"], "bid_id": out["bid"], "bid_price": bid_price,
            "min_qty": min_qty, "phone": phone, "job": dict(job) if job else None}


async def main(args) -> int:
    pool = await db.connect()
    await cache.connect()
    try:
        phone = await pick_phone(pool, args.phone)
        print(f"database: {settings.database_url.rsplit('/', 1)[1]} | real phone: {mask(phone)} | bid {args.price} Rs/qtl")
        async with httpx.AsyncClient(base_url=args.base, timeout=30) as http:
            try:
                health = (await http.get("/health")).json()
            except Exception as e:
                raise Stop(f"The backend at {args.base} is not answering ({type(e).__name__}). Start it first.")
            print(f"server: provider={health.get('provider')}")
            if health.get("provider") != "exotel":
                print("  WARNING: the server is not using Exotel (TELEPHONY_PROVIDER), so no real call will be placed.")
            if args.dry_run:
                row = await pool.fetchrow("SELECT id::text FROM farmers WHERE phone = $1", phone)
                cl = await my_cluster(pool, row["id"]) if row else None
                print(f"dry run: farmer registered={bool(row)}, ragi cluster={'#%s %s' % (cl['code'], cl['status']) if cl else 'none yet'}" + (' -> the stranded lot would be released and a fresh 5 q lot listed' if cl and cl['status'] in ('NO_BID', 'FAILED') else (' -> a 5 q lot would be listed' if not cl else '')) + ". Nothing changed.")
                return 0
            r = await run(pool, http, phone, args.price)
        j = r["job"]
        print("\nRESULT")
        print(f"  cluster {r['cluster_id']}  (#{r['cluster_code']})   bid Rs {r['bid_price']}/qtl   min qty {r['min_qty']:g} q")
        if j and j["provider_call_id"]:
            print(f"  Exotel accepted the call: call id {j['provider_call_id']} (job {j['status']}). Your phone is ringing: press 1, then 1.")
        elif j:
            print(f"  Exotel call NOT placed: job {j['status']}, reason {j['last_error']} (attempt {j['attempts']}).")
        else:
            print("  No call job was created for that phone.")
        return 0 if j and j["provider_call_id"] else 2
    except Stop as e:
        print(f"STOPPED: {e}")
        return 1
    finally:
        await cache.close()
        await db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone")
    ap.add_argument("--price", type=int, default=3850)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--dry-run", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args())))
