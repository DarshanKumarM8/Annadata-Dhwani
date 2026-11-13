"""Register a phone as a farmer so it gets the real listing flow (not the "not registered" message). Owner: Darshan.

  python backend/scripts/add_farmer.py --phone 9876543210            # 10 digits, 0+10 digits or +91... all accepted
  python backend/scripts/add_farmer.py --last-unknown                # register the number that most recently called as unknown

The farmer is put on the first collection point in the database. Re-running is harmless. It also clears the
"unknown caller" block, the 20 s dedupe and the call counters for that number so the next missed call is answered at once.
Run it against the dev database (not annadata_test).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402

from app.config import settings  # noqa: E402
from app.telephony.exotel import normalise  # noqa: E402


def mask(p: str) -> str:
    return p[:5] + "****" + p[-3:]


async def main(phone: str | None, last_unknown: bool, name: str, village: str) -> None:
    c = await asyncpg.connect(settings.database_url)
    try:
        if last_unknown:
            phone = await c.fetchval("""SELECT phone FROM call_sessions WHERE kind = 'UNKNOWN_CALLER'
                                        ORDER BY started_at DESC LIMIT 1""")
            if not phone:
                sys.exit("No unknown caller has called yet.")
        else:
            phone = normalise(phone or "")
            if not phone:
                sys.exit("That does not look like an Indian mobile number.")
        cp = await c.fetchrow("""SELECT cp.id, cp.fpo_id, cp.district_code, ST_X(cp.geog::geometry) AS lon,
                                        ST_Y(cp.geog::geometry) AS lat
                                 FROM collection_points cp ORDER BY cp.name LIMIT 1""")
        if not cp:
            sys.exit("No collection point in the database: run a seed first.")
        done = await c.execute("""INSERT INTO farmers (phone, name, fpo_id, village, district_code, geog, collection_point_id)
            VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326)::geography, $8)
            ON CONFLICT (phone) DO NOTHING""", phone, name, cp["fpo_id"], village, cp["district_code"],
                               cp["lon"], cp["lat"], cp["id"])
        print(f"{mask(phone)}: " + ("registered as a farmer" if done.endswith("1") else "was already a farmer"))
    finally:
        await c.close()
    r = aioredis.from_url(settings.redis_url)
    await r.delete(f"unk:{phone}", f"miss:{phone}", f"rl:cb:{phone}:10m", f"rl:cb:{phone}:day", f"fail:{phone}",
                   f"sess:{phone}", f"lock:call:{phone}")
    await r.aclose()
    print("blocks cleared: the next missed call from this number is answered with a callback")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phone")
    ap.add_argument("--last-unknown", action="store_true")
    ap.add_argument("--name", default="Team Phone")
    ap.add_argument("--village", default="Keregodu")
    a = ap.parse_args()
    if not (a.phone or a.last_unknown):
        ap.error("give --phone or --last-unknown")
    asyncio.run(main(a.phone, a.last_unknown, a.name, a.village))
