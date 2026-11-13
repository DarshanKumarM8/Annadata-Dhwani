"""Close a cluster's auction for the live demo: only REAL phones get a confirmation call. Owner: Darshan.

  python backend/scripts/close_for_demo.py 121                 # cluster code (the C-121 number on the buyer screen)
  python backend/scripts/close_for_demo.py 121 --dry-run       # show what would happen, change nothing

What it does, in this order:
  1. finds the cluster's leading bid and its lots, and tells simulator farmers (+919800000001..08, who have no phone on the
     real network) apart from real farmers;
  2. pre-empts the call queue for the simulator lots, so Exotel is never asked to dial those numbers;
  3. closes the auction through the admin API (the running server rings the real phones);
  4. records ACCEPT for the simulator lots (they stand in for farmers who are not on the phone).
The real farmers' lots stay PENDING: their phones ring and they answer 1 then 1. The round settles when all lots have answered
(or after the 90 s confirmation deadline). Use --reject-simulators to make the simulated farmers refuse instead.
Needs the backend running (default http://localhost:8000) and SEED_PASSWORD in .env.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app import cache, db  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import bidding  # noqa: E402

SIMULATOR_PHONES = {f"+91980000000{n}" for n in range(1, 9)}


def mask(p: str) -> str:
    return p[:5] + "****" + p[-3:]


async def lots_of(pool, cluster_id: str) -> list[dict]:
    rows = await pool.fetch("""SELECT l.id::text AS listing_id, l.qty_qtl, l.ask_price, f.id::text AS farmer_id, f.phone
                               FROM listings l JOIN farmers f ON f.id = l.farmer_id
                               WHERE l.cluster_id = $1::uuid AND l.status = 'ACTIVE' ORDER BY l.ask_price""", cluster_id)
    return [dict(r) for r in rows]


async def close_with_simulated_farmers(pool, cluster_id: str, closer, sim_phones=SIMULATOR_PHONES, accept=True) -> dict:
    """`closer` is an async callable that closes the auction (the admin API in the CLI, bidding.close_auction in tests)."""
    c = await pool.fetchrow("SELECT status, best_bid_id::text AS bid FROM clusters WHERE id = $1::uuid", cluster_id)
    if not c or c["status"] != "BIDDING" or not c["bid"]:
        return {"error": f"cluster is {c['status'] if c else 'missing'} with {'a' if c and c['bid'] else 'no'} leading bid: "
                         "it must be BIDDING with a bid before it can be closed"}
    lots = await lots_of(pool, cluster_id)
    sim = [x for x in lots if x["phone"] in sim_phones]
    real = [x for x in lots if x["phone"] not in sim_phones]
    # (2) pre-empt the queue: the job rows exist already as CANCELLED, so close_auction's insert skips them (same dedupe key)
    for x in sim:
        await pool.execute("""INSERT INTO call_jobs (phone, farmer_id, kind, payload, dedupe_key, status, last_error)
                              VALUES ($1, $2::uuid, 'BID_OFFER', $3, $4, 'CANCELLED', 'SIMULATED_FARMER')
                              ON CONFLICT (dedupe_key) DO NOTHING""",
                           x["phone"], x["farmer_id"], json.dumps({"bid_id": c["bid"], "listing_id": x["listing_id"]}),
                           f"bid:{c['bid']}:{x['listing_id']}")
    await closer(cluster_id)                                                  # (3) real farmers' phones start ringing
    after = await pool.fetchval("SELECT status FROM clusters WHERE id = $1::uuid", cluster_id)
    for x in sim:                                                             # (4) simulator farmers answer for themselves
        await bidding.record_response(pool, c["bid"], x["listing_id"], "ACCEPT" if accept else "REJECT")
    return {"bid": c["bid"], "status_after_close": after, "simulated": len(sim), "real": [x["phone"] for x in real],
            "sim_qtl": sum(float(x["qty_qtl"]) for x in sim), "real_qtl": sum(float(x["qty_qtl"]) for x in real)}


async def main(code: int, base: str, dry: bool, accept: bool) -> int:
    pool = await db.connect()
    await cache.connect()
    try:
        c = await pool.fetchrow("""SELECT cl.id::text AS id, cl.status, cl.total_qtl, b.price_per_qtl, b.min_qty_qtl, bu.email
                                   FROM clusters cl LEFT JOIN bids b ON b.id = cl.best_bid_id LEFT JOIN buyers bu ON bu.id = b.buyer_id
                                   WHERE cl.code = $1""", code)
        if not c:
            print(f"No cluster with code {code}.")
            return 1
        print(f"cluster #{code}: {c['status']}, {float(c['total_qtl']):g} q" +
              (f", leading bid Rs {float(c['price_per_qtl']):.0f} (min {float(c['min_qty_qtl']):g} q) by {c['email']}" if c["price_per_qtl"] else ", NO bid"))
        if c["status"] != "BIDDING" or not c["price_per_qtl"]:
            print("Not ready: the cluster must be BIDDING (agent verified) with a leading bid. Nothing was changed.")
            return 1
        lots = await lots_of(pool, c["id"])
        for x in lots:
            print(f"  lot {float(x['qty_qtl']):g} q @ {float(x['ask_price']):.0f}  {mask(x['phone'])}  -> " +
                  ("simulated farmer: will auto-" + ("accept" if accept else "reject") if x["phone"] in SIMULATOR_PHONES else "REAL phone: will be called"))
        if dry:
            print("dry run: nothing changed")
            return 0

        async def closer(cid):
            async with httpx.AsyncClient(base_url=base, timeout=30) as h:
                tok = (await h.post("/api/auth/buyer/login", json={"email": "admin@demo.test", "password": os.getenv("SEED_PASSWORD", "")})).json()["token"]
                r = await h.post(f"/api/admin/clusters/{cid}/close-auction", headers={"Authorization": f"Bearer {tok}"})
                print("close-auction ->", r.status_code, r.text[:80])

        out = await close_with_simulated_farmers(pool, c["id"], closer, accept=accept)
        if "error" in out:
            print(out["error"])
            return 1
        print(f"\nauction closed: cluster is now {out['status_after_close']}. {out['simulated']} simulated lot(s) "
              f"({out['sim_qtl']:g} q) {'accepted' if accept else 'rejected'}; waiting for {len(out['real'])} real phone(s) "
              f"({out['real_qtl']:g} q): {', '.join(mask(p) for p in out['real']) or 'none'}")
        print("Answer the call: press 1, then 1 again. The round settles when every lot has answered (deadline: 90 s).")
        return 0
    finally:
        await cache.close()
        await db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("code", type=int, help="cluster code shown on the buyer screen, e.g. 121")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reject-simulators", action="store_true")
    a = ap.parse_args()
    print(f"database: {settings.database_url.rsplit('/', 1)[1]}")
    sys.exit(asyncio.run(main(a.code, a.base, a.dry_run, not a.reject_simulators)))
