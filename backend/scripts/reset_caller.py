"""Put a phone number back to a brand-new first-time farmer. Owner: Darshan.

  python backend/scripts/reset_caller.py                       # every number in TEAM_PHONES (.env)
  python backend/scripts/reset_caller.py +919876543210         # that number (registered if it is new), plus TEAM_PHONES
  python backend/scripts/reset_caller.py 9876543210 --keep-listings
  python backend/scripts/reset_caller.py --only +919876543210  # just that number, not TEAM_PHONES

For each number it:
  - clears the Redis keys of that number (session, call lock, missed-call dedupe, failure count, callback limits, the
    unknown-caller block, and every Exotel call-id entry that points at it);
  - deletes its call sessions and key-press evidence, call jobs, helper tickets and consent records;
  - unless --keep-listings: deletes its listings and bid answers, then recomputes the affected clusters (a READY cluster that
    falls under 20 quintals goes back to OPEN; an empty one with no bids is removed). Lots that sit in an auction that is
    running or in a deal are never deleted (they are reported as kept);
  - registers the number if it is new, and clears language and consent so the next call starts at the welcome and language menu.
Run against the dev database. Dashboards refresh by themselves.
"""
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cache, db  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import clustering, events, views  # noqa: E402
from app.telephony.exotel import normalize_e164  # noqa: E402

PROTECTED = ("BIDDING", "CONFIRMING", "DEAL")          # lots in a running auction or a deal are not touched


def mask(p: str) -> str:
    return p[:5] + "****" + p[-3:]


async def clear_redis(phone: str) -> int:
    r = cache.redis
    keys = [f"sess:{phone}", f"lock:call:{phone}", f"miss:{phone}", f"fail:{phone}", f"rl:cb:{phone}:10m",
            f"rl:cb:{phone}:day", f"unk:{phone}"]
    async for k in r.scan_iter("callmap:exotel:*", count=500):
        if not k.endswith(":job") and await r.get(k) == phone:
            keys += [k, k + ":job"]
    return int(await r.delete(*keys))


async def reset_phone(pool, phone: str, keep_listings: bool = False) -> dict:
    out = {"phone": phone, "redis_keys": await clear_redis(phone), "listings_cleared": 0, "listings_kept": 0,
           "clusters_changed": 0, "registered_now": False}
    seqs: list[int] = []
    resync = False
    async with pool.acquire() as conn, conn.transaction():
        farmer = await conn.fetchrow("SELECT id FROM farmers WHERE phone = $1", phone)
        if not farmer:
            cp = await conn.fetchrow("""SELECT id, fpo_id, district_code, ST_X(geog::geometry) AS lon, ST_Y(geog::geometry) AS lat
                                        FROM collection_points ORDER BY name LIMIT 1""")
            if not cp:
                raise SystemExit("No pickup point in the database: run a seed first.")
            farmer = await conn.fetchrow("""INSERT INTO farmers (phone, name, fpo_id, village, district_code, geog, collection_point_id)
                VALUES ($1, 'Team Phone', $2, 'Keregodu', $3, ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography, $6)
                RETURNING id""", phone, cp["fpo_id"], cp["district_code"], cp["lon"], cp["lat"], cp["id"])
            out["registered_now"] = True
        fid = farmer["id"]

        if not keep_listings:
            lots = await conn.fetch("""SELECT l.id, l.cluster_id, cl.status, cl.collection_point_id, cl.crop_code
                                       FROM listings l JOIN clusters cl ON cl.id = l.cluster_id WHERE l.farmer_id = $1""", fid)
            doomed = [x for x in lots if x["status"] not in PROTECTED]
            out["listings_kept"] = len(lots) - len(doomed)
            for cl in {(x["cluster_id"], x["collection_point_id"], x["crop_code"]) for x in doomed}:
                await clustering.lock_key(conn, cl[1], cl[2])              # same lock order as listing and bidding
            if doomed:
                ids = [x["id"] for x in doomed]
                await conn.execute("DELETE FROM bid_responses WHERE listing_id = ANY($1)", ids)
                await conn.execute("DELETE FROM listings WHERE id = ANY($1)", ids)
                out["listings_cleared"] = len(ids)
            for cid in {x["cluster_id"] for x in doomed}:
                await clustering.recompute_cluster(conn, cid)
                c = await conn.fetchrow("""SELECT status, listing_count, total_qtl,
                                           (SELECT count(*) FROM bids WHERE cluster_id = clusters.id) AS bids
                                           FROM clusters WHERE id = $1""", cid)
                if c["listing_count"] == 0 and c["bids"] == 0 and c["status"] in ("OPEN", "READY", "NO_BID", "FAILED", "CLOSED"):
                    await conn.execute("DELETE FROM clusters WHERE id = $1", cid)
                    resync = True                                            # a vanished cluster needs a dashboard refetch
                else:
                    if c["status"] == "READY" and float(c["total_qtl"]) < clustering.READY_QTL:
                        await conn.execute("UPDATE clusters SET status = 'OPEN', version = version + 1 WHERE id = $1", cid)
                    seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, cid)))
                out["clusters_changed"] += 1

        # a listing points back at the call that made it: detach the ones that stay, then the sessions can go
        await conn.execute("UPDATE listings SET session_id = NULL WHERE farmer_id = $1 AND session_id IS NOT NULL", fid)
        await conn.execute("DELETE FROM dtmf_events WHERE session_id IN (SELECT id FROM call_sessions WHERE phone = $1)", phone)
        await conn.execute("DELETE FROM call_sessions WHERE phone = $1", phone)
        await conn.execute("DELETE FROM call_jobs WHERE phone = $1 OR farmer_id = $2", phone, fid)
        await conn.execute("DELETE FROM triage_tickets WHERE phone = $1 OR farmer_id = $2", phone, fid)
        await conn.execute("DELETE FROM consent_log WHERE farmer_id = $1", fid)

        await conn.execute("""UPDATE farmers SET lang = NULL, consent_version = NULL, consent_at = NULL, status = 'ACTIVE'
                              WHERE id = $1""", fid)
        st = await conn.fetchrow("SELECT lang, consent_at, district_code FROM farmers WHERE id = $1", fid)
        out["state"] = f"lang={st['lang']}, consent={st['consent_at']}, district={st['district_code']}"
    await events.publish(seqs)
    if resync:
        await cache.redis.publish("ad:events", "resync")
    return out


def targets(cli: list[str], only: bool) -> list[str]:
    raw = list(cli) + ([] if only else [p for p in re.split(r"[,;\s]+", os.getenv("TEAM_PHONES", "")) if p])
    seen: list[str] = []
    for r in raw:
        n = normalize_e164(r)
        if not n:
            print(f"skipped (not an Indian mobile number): {r!r}")
        elif n not in seen:
            seen.append(n)
    return seen


async def main(args) -> int:
    phones = targets(args.phones, args.only)
    if not phones:
        print("No phone numbers: pass some, or set TEAM_PHONES in .env.")
        return 1
    pool = await db.connect()
    await cache.connect()
    try:
        print(f"database: {settings.database_url.rsplit('/', 1)[1]} | {len(phones)} number(s) | "
              f"listings: {'kept' if args.keep_listings else 'cleared'}\n")
        print(f"{'phone':<14} {'new?':<5} {'redis keys':<11} {'listings':<22} {'state now'}")
        for p in phones:
            r = await reset_phone(pool, p, args.keep_listings)
            lst = f"{r['listings_cleared']} cleared" + (f", {r['listings_kept']} kept (auction/deal)" if r["listings_kept"] else "")
            print(f"{mask(p):<14} {'yes' if r['registered_now'] else 'no':<5} {r['redis_keys']:<11} {lst:<22} {r['state']}")
        print("\nNext call from each number starts as a first-time farmer: welcome, language menu, consent, crop menu.")
        return 0
    finally:
        await cache.close()
        await db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phones", nargs="*", help="numbers to reset in addition to TEAM_PHONES")
    ap.add_argument("--only", action="store_true", help="reset only the numbers given, not TEAM_PHONES")
    ap.add_argument("--keep-listings", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args())))
