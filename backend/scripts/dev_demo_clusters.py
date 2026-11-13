"""Demo clusters for the buyer dashboard. Owner: Darshan. (Anirudh's seed_demo.py may supersede this.)

Creates three clusters through the real listing code, so they behave like clusters made by phone calls:
  Ragi   25 q from 5 farmers -> READY    (an agent has a VERIFY task; try the verification on /demo)
  Maize  12 q from 3 farmers -> OPEN     (12 of 20 quintals, still filling)
  Paddy  24 q from 3 farmers -> BIDDING  (open for bids for 2 hours; verification is faked in the database)

Needs the eight simulator farmers (python backend/scripts/dev_min_seed.py first).
  python backend/scripts/dev_demo_clusters.py            # wipes the trade data of those eight farmers, then seeds
  python backend/scripts/dev_demo_clusters.py --clear    # only wipes
Run it against the dev database (not annadata_test). A running server picks the new clusters up live.
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, db  # noqa: E402
from app.services import clustering, events, views  # noqa: E402

PHONES = [f"+91980000000{n}" for n in range(1, 9)]
# (crop, [(farmer number 1-8, quintals, ask rupees per quintal), ...])
PLAN = [
    ("ragi", [(1, 5, 3550), (2, 5, 3565), (3, 5, 3580), (4, 5, 3590), (5, 5, 3600)]),
    ("maize", [(6, 4, 2200), (7, 4, 2220), (8, 4, 2240)]),
    ("paddy_common", [(1, 8, 2300), (2, 8, 2310), (3, 8, 2320)]),
]


async def clear(pool) -> None:
    async with pool.acquire() as c, c.transaction():
        farmers = "(SELECT id FROM farmers WHERE phone = ANY($1))"
        await c.execute(f"DELETE FROM bid_responses WHERE listing_id IN (SELECT id FROM listings WHERE farmer_id IN {farmers})", PHONES)
        await c.execute(f"DELETE FROM call_jobs WHERE farmer_id IN {farmers}", PHONES)
        await c.execute(f"DELETE FROM listings WHERE farmer_id IN {farmers}", PHONES)
        empty = "(SELECT c.id FROM clusters c WHERE NOT EXISTS (SELECT 1 FROM listings l WHERE l.cluster_id = c.id))"
        await c.execute(f"UPDATE clusters SET best_bid_id = NULL WHERE id IN {empty}")
        await c.execute(f"DELETE FROM deals WHERE cluster_id IN {empty}")
        await c.execute(f"DELETE FROM bid_responses WHERE bid_id IN (SELECT id FROM bids WHERE cluster_id IN {empty})")
        await c.execute(f"DELETE FROM bids WHERE cluster_id IN {empty}")
        await c.execute(f"DELETE FROM verifications WHERE cluster_id IN {empty}")
        await c.execute(f"DELETE FROM clusters WHERE id IN {empty}")
        await c.execute("DELETE FROM call_sessions WHERE phone = ANY($1)", PHONES)
    for p in PHONES:
        await cache.redis.delete(f"sess:{p}", f"fail:{p}", f"miss:{p}")


async def seed(pool) -> None:
    ids = {r["phone"]: str(r["id"]) for r in await pool.fetch("SELECT id, phone FROM farmers WHERE phone = ANY($1)", PHONES)}
    if len(ids) < 8:
        sys.exit("The eight simulator farmers are missing: run python backend/scripts/dev_min_seed.py first.")
    for crop, lots in PLAN:
        for n, qty, price in lots:
            phone = PHONES[n - 1]
            await clustering.commit_listing(pool, {
                "id": str(uuid.uuid4()), "phone": phone, "farmer_id": ids[phone], "kind": "LISTING", "provider": "sim",
                "call_id": "demo-" + uuid.uuid4().hex[:6], "state": "DONE", "version": 1,
                "data": {"crop": crop, "qty": qty, "price": price}})
    # paddy: pretend the agent already verified it, so there is a cluster open for bids
    paddy = await pool.fetchval("SELECT id FROM clusters WHERE crop_code = 'paddy_common' AND status = 'READY'")
    async with pool.acquire() as c, c.transaction():
        await c.execute("""UPDATE clusters SET status = 'BIDDING', grade = 'B', version = version + 1,
                           bidding_ends_at = now() + interval '2 hours', updated_at = now() WHERE id = $1""", paddy)
        seq = await events.emit(c, "cluster.updated", await views.cluster_view(c, paddy))
    await events.publish([seq])                       # open dashboards see it turn to BIDDING


async def main(only_clear: bool) -> None:
    pool = await db.connect()
    await cache.connect()
    try:
        await clear(pool)
        if not only_clear:
            await seed(pool)
        for r in await pool.fetch("SELECT code, crop_code, status, total_qtl, listing_count FROM clusters ORDER BY code"):
            print(f"  cluster #{r['code']:<4} {r['crop_code']:<13} {r['status']:<8} {float(r['total_qtl']):>5} q  {r['listing_count']} farmers")
    finally:
        await cache.close()
        await db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true")
    asyncio.run(main(ap.parse_args().clear))
