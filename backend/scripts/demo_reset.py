"""Reset the demo to a known state in a few seconds. Owner: Darshan.

  python backend/scripts/demo_reset.py --yes              # wipe trade data, reseed, rebuild the three demo clusters
  python backend/scripts/demo_reset.py --yes --empty      # same, but no clusters (clean start for the acceptance run)
  python backend/scripts/demo_reset.py --yes --keep-farmers   # keep farmers' language/consent (skips the first-call menus)

Wipes: listings, clusters, bids, deals, verifications, call jobs/sessions/evidence, helper tickets, consent log, the event
feed, and the Redis keys that belong to calls (sessions, counters, locks, price floors).
Keeps: reference data, farmers, buyers, agents. Then reseeds reference rows and the price floor, optionally the demo
clusters, and tells connected dashboards to refetch (they receive {"type":"resync"}).
Works against whichever DATABASE_URL is configured: it prints the database name first.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import redis.asyncio as aioredis  # noqa: E402

import dev_demo_clusters  # noqa: E402
import dev_min_seed  # noqa: E402
from app import cache, db  # noqa: E402
from app.config import settings  # noqa: E402

WIPE = [
    "DELETE FROM ledger",
    "DELETE FROM bid_responses",
    "DELETE FROM deals",
    "UPDATE clusters SET best_bid_id = NULL",
    "DELETE FROM bids",
    "DELETE FROM verifications",
    "DELETE FROM call_jobs",
    "DELETE FROM listings",
    "DELETE FROM clusters",
    "DELETE FROM dtmf_events",
    "DELETE FROM call_sessions",
    "DELETE FROM triage_tickets",
    "DELETE FROM consent_log",
    "DELETE FROM events",
    "DELETE FROM price_floors",
]
REDIS_PATTERNS = ["sess:*", "fail:*", "miss:*", "unk:*", "rl:*", "budget:*", "lock:call:*", "evt:*", "callmap:*",
                  "exo:*", "floor:*"]


async def main(empty: bool, keep_farmers: bool) -> None:
    t0 = time.time()
    pool = await db.connect()
    await cache.connect()
    try:
        async with pool.acquire() as c, c.transaction():
            for q in WIPE:
                await c.execute(q)
            if not keep_farmers:
                await c.execute("UPDATE farmers SET lang = NULL, consent_version = NULL, consent_at = NULL")
        n = 0
        for pat in REDIS_PATTERNS:
            async for k in cache.redis.scan_iter(pat, count=500):
                await cache.redis.delete(k)
                n += 1
        cache.load_scripts()
        print(f"wiped trade data and {n} redis keys ({time.time() - t0:.1f}s)")
        from app.services import pricing                                              # a reference price for every crop, offline and fast
        print(f"loaded {await pricing.refresh(pool, cache.redis, live=False)} mandi price floors from the saved samples")
    finally:
        await cache.close()
        await db.close()

    await dev_min_seed.main(3565, False)                  # reference rows, buyers, agent, price floor (re-cached)
    if not empty:
        await dev_demo_clusters.main(False)               # ragi READY, maize OPEN, paddy BIDDING
    r = aioredis.from_url(settings.redis_url)
    await r.publish("ad:events", "resync")                # open dashboards refetch
    await r.aclose()
    print(f"demo reset done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--empty", action="store_true", help="no demo clusters")
    ap.add_argument("--keep-farmers", action="store_true")
    a = ap.parse_args()
    name = settings.database_url.rsplit("/", 1)[1]
    if not a.yes:
        if input(f"This wipes the trade data in database '{name}'. Type RESET to continue: ").strip() != "RESET":
            sys.exit("cancelled")
    else:
        print(f"resetting database '{name}'")
    asyncio.run(main(a.empty, a.keep_farmers))
