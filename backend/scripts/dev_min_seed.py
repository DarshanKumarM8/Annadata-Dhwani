"""Minimal reference data so D2-D4 can run before Anirudh's db/002_reference.sql lands. Owner: Darshan.

Idempotent (ON CONFLICT DO NOTHING). Anirudh's seed supersedes this; do not run both against one database
unless the keys match (district KA-MANDYA, crops ragi / paddy_common / maize).

  python scripts/dev_min_seed.py                # reference rows + test farmer +919800000001
  python scripts/dev_min_seed.py --floor 3565   # also cache a ragi price floor (dev only; pricing.py owns floor:* later)
  python scripts/dev_min_seed.py --reset        # delete this farmer's listings/sessions/tickets and the Redis session
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402
import bcrypt  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402

from app.config import settings  # noqa: E402

PHONE = "+919800000001"
FPO_ID = "00000000-0000-4000-8000-0000000000f0"
CP_ID = "00000000-0000-4000-8000-0000000000c1"
FARMER_ID = "00000000-0000-4000-8000-0000000000a1"


async def main(floor: int | None, reset: bool) -> None:
    c = await asyncpg.connect(settings.database_url)
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    if reset:
        # clear this farmer's listings and any trade built on them (responses, bids, deals, verifications, clusters)
        await c.execute("DELETE FROM bid_responses WHERE listing_id IN (SELECT id FROM listings WHERE farmer_id = $1::uuid)",
                        FARMER_ID)
        await c.execute("DELETE FROM listings WHERE farmer_id = $1::uuid", FARMER_ID)
        empty = "(SELECT c.id FROM clusters c WHERE NOT EXISTS (SELECT 1 FROM listings l WHERE l.cluster_id = c.id))"
        await c.execute(f"UPDATE clusters SET best_bid_id = NULL WHERE id IN {empty}")
        await c.execute(f"DELETE FROM deals WHERE cluster_id IN {empty}")
        await c.execute(f"DELETE FROM bid_responses WHERE bid_id IN (SELECT id FROM bids WHERE cluster_id IN {empty})")
        await c.execute(f"DELETE FROM bids WHERE cluster_id IN {empty}")
        await c.execute(f"DELETE FROM verifications WHERE cluster_id IN {empty}")
        await c.execute(f"DELETE FROM clusters WHERE id IN {empty}")
        await c.execute("DELETE FROM call_sessions WHERE phone = $1", PHONE)
        await c.execute("DELETE FROM triage_tickets WHERE phone = $1", PHONE)
        await c.execute("DELETE FROM consent_log WHERE farmer_id = $1::uuid", FARMER_ID)
        await c.execute("UPDATE farmers SET lang = NULL, consent_version = NULL, consent_at = NULL WHERE id = $1::uuid",
                        FARMER_ID)
        await r.delete(f"sess:{PHONE}", f"fail:{PHONE}")
    await c.execute("""INSERT INTO districts VALUES ('KA-MANDYA','Mandya','Karnataka','Karnataka','Mandya','kn')
                       ON CONFLICT DO NOTHING""")
    await c.execute("""INSERT INTO crops (code,name_en,agmark_name,msp,max_listing_qtl,min_price,max_price) VALUES
        ('ragi','Ragi','Ragi (Finger Millet)',5205,50,1500,9000),
        ('paddy_common','Paddy','Paddy(Dhan)(Common)',2441,50,1000,5000),
        ('maize','Maize','Maize',2410,50,1000,5000) ON CONFLICT DO NOTHING""")
    for rank, crop in enumerate(["ragi", "paddy_common", "maize"], start=1):
        for month in (10, 11, 12):
            await c.execute("INSERT INTO crop_calendar VALUES ('KA-MANDYA',$1,$2,$3) ON CONFLICT DO NOTHING",
                            month, crop, rank)
    await c.execute("""INSERT INTO deduction_rules VALUES ('KA-MANDYA',50,10,0.02,'assumed, to confirm with FPO')
                       ON CONFLICT DO NOTHING""")
    await c.execute("INSERT INTO fpos (id,name,district_code,payee_details) VALUES ($1::uuid,'Dev FPO','KA-MANDYA','UPI dev@bank') "
                    "ON CONFLICT DO NOTHING", FPO_ID)
    await c.execute("""INSERT INTO collection_points (id,fpo_id,name,district_code,geog)
        VALUES ($1::uuid,$2::uuid,'Dev FPO yard','KA-MANDYA', ST_SetSRID(ST_MakePoint(76.90,12.52),4326)::geography)
        ON CONFLICT DO NOTHING""", CP_ID, FPO_ID)
    await c.execute("""INSERT INTO farmers (id,phone,name,fpo_id,village,district_code,geog,collection_point_id)
        VALUES ($1::uuid,$2,'Dev Farmer',$3::uuid,'Keregodu','KA-MANDYA',
                ST_SetSRID(ST_MakePoint(76.91,12.53),4326)::geography,$4::uuid) ON CONFLICT DO NOTHING""",
                    FARMER_ID, PHONE, FPO_ID, CP_ID)
    pw = bcrypt.hashpw(os.getenv("SEED_PASSWORD", "change-me").encode(), bcrypt.gensalt(rounds=10)).decode()
    for email, org in (("buyer1@demo.test", "Mysuru Grain Traders"), ("buyer2@demo.test", "Bengaluru Agro Foods"),
                       ("admin@demo.test", "Platform Admin")):
        await c.execute("""INSERT INTO buyers (org_name,email,password_hash,phone,status)
                           VALUES ($1,$2,$3,'+910000000000','APPROVED')
                           ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash""", org, email, pw)
    pin = bcrypt.hashpw(os.getenv("AGENT_PIN", "1234").encode(), bcrypt.gensalt(rounds=10)).decode()
    await c.execute("""INSERT INTO agents (fpo_id,name,phone,pin_hash) VALUES ($1::uuid,'Kavya','+919800000099',$2)
                       ON CONFLICT (phone) DO UPDATE SET pin_hash = EXCLUDED.pin_hash""", FPO_ID, pin)
    if floor:
        afpp = int((floor * 0.98 - 60) // 10 * 10)
        await r.set("floor:KA-MANDYA:ragi", json.dumps({"modal_price": float(floor), "afpp": afpp,
                    "basis": "DISTRICT_FRESH", "price_date": "dev"}), ex=93600)
        print(f"cached ragi floor: modal {floor}, afpp {afpp}")
    print("seed ok; farmer", PHONE)
    await c.close()
    await r.aclose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=int)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.floor, a.reset))
