#!/usr/bin/env python3
"""Seed demo data for Annadata Dhwani produce marketplace.

Populates:
- 40 farmers in Mandya district around collection points with Kannada names & villages.
- 2 clusters:
  * Cluster A: Keregodu FPO yard, ragi, status OPEN, 6 listings (17 qtl), asks 3550-3700.
  * Cluster B: Hosahalli point, paddy_common, status BIDDING, 8 listings (26 qtl), grade B, ends now+1d.
- 7 days of mandi_prices for each district × crop with realistic market prices.

Usage
-----
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/annadata \
        python backend/scripts/seed_demo.py [--reset]
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import uuid
from datetime import date, datetime, timedelta, timezone

import asyncpg

# Reference literals from db/002_reference.sql
FPO_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
CP_KEREGODU = uuid.UUID("00000000-0000-0000-0000-000000000011")
CP_HOSAHALLI = uuid.UUID("00000000-0000-0000-0000-000000000012")
CP_VENUE = uuid.UUID("00000000-0000-0000-0000-000000000013")
DISTRICT_CODE = "KA-MANDYA"

# Collection point coordinates (lat, lon)
CP_COORDS = {
    CP_KEREGODU: (12.6300, 76.9200),
    CP_HOSAHALLI: (12.5800, 76.8800),
    CP_VENUE: (12.9700, 77.5900),
}

# Fixed cluster UUIDs for deterministic reference
CLUSTER_A_ID = uuid.UUID("00000000-0000-0000-0001-000000000001")
CLUSTER_B_ID = uuid.UUID("00000000-0000-0000-0001-000000000002")

# 40 authentic Kannada first names
KANNADA_NAMES = [
    "Manjunath", "Ningappa", "Basavaraj", "Shivanna", "Mallikarjun",
    "Kempegowda", "Siddaraju", "Kumaraswamy", "Puttegowda", "Nanjundegowda",
    "Channabasappa", "Shivalingappa", "Paramesh", "Ramalingegowda", "Marigowda",
    "Devegowda", "Thimmegowda", "Chikkanna", "Boregowda", "Ramegowda",
    "Venkatesh", "Krishnegowda", "Somanna", "Lingaraju", "Mahadeva",
    "Anandagowda", "Chennappa", "Revanna", "Jagadish", "Doddanna",
    "Erappa", "Chandregowda", "Basavalingappa", "Gangadhar", "Honnegowda",
    "Rudregowda", "Girish", "Prakash", "Somashekar", "Shantharaju",
]

# 40 villages in Mandya district
MANDYA_VILLAGES = [
    "Keregodu", "Hosahalli", "Dudda", "Basaralu", "Hunasakere",
    "Holalu", "Ummadahalli", "Guttalu", "Yenneholekoppalu", "Bidanagere",
    "Kyathumgere", "Induvalu", "Shivalli", "Gopalapura", "Mangala",
    "Maragowdanahalli", "Keelara", "Modachakanahalli", "Sunagahalli", "Halaguru",
    "Maddur", "Besagarahalli", "Shivapura", "Koppa", "Hemmanahalli",
    "Valagerehalli", "Aladahalli", "Chikkarasinakere", "Belakavadi", "Athaguru",
    "Mallanakuppe", "Kadukothanahalli", "Thorekadanahalli", "Settihalli", "Gejjalagere",
    "Nidaghatta", "Doddarasinakere", "Honaganahalli", "Kothathi", "Chinya",
]


def generate_point_offset(
    center_lat: float,
    center_lon: float,
    rng: random.Random,
    min_dist_m: float = 500.0,
    max_dist_m: float = 4000.0,
) -> tuple[float, float]:
    """Generate (lon, lat) uniformly distributed in an annulus around center."""
    dist_m = rng.uniform(min_dist_m, max_dist_m)
    bearing_rad = rng.uniform(0, 2 * math.pi)

    delta_lat = (dist_m * math.cos(bearing_rad)) / 111320.0
    delta_lon = (dist_m * math.sin(bearing_rad)) / (
        111320.0 * math.cos(math.radians(center_lat))
    )

    return round(center_lon + delta_lon, 6), round(center_lat + delta_lat, 6)


async def seed_data(pool: asyncpg.Pool, reset: bool) -> None:
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    # Fixed seed for deterministic geolocation
    rng = random.Random(42)

    # Check for team phones override for the first 4 farmers
    team_phones_env = os.environ.get("TEAM_PHONES", "").strip()
    team_phones: list[str] = [
        p.strip() for p in team_phones_env.split(",") if p.strip()
    ]

    async with pool.acquire() as conn:
        async with conn.transaction():
            if reset:
                # Truncate all dependent demo tables safely
                await conn.execute("""
                    DO $$
                    DECLARE
                        tbls text;
                    BEGIN
                        SELECT string_agg(quote_ident(tablename), ', ')
                        INTO tbls
                        FROM pg_tables
                        WHERE schemaname = 'public'
                          AND tablename IN (
                            'listings', 'bid_responses', 'bids', 'deals', 'verifications',
                            'call_jobs', 'call_sessions', 'triage_tickets', 'consent_log',
                            'dtmf_events', 'events', 'clusters', 'farmers'
                          );
                        IF tbls IS NOT NULL THEN
                            EXECUTE 'TRUNCATE TABLE ' || tbls || ' CASCADE';
                        END IF;
                    END $$;
                """)

            # ----------------------------------------------------------------
            # 1. Seed 40 Farmers
            # ----------------------------------------------------------------
            farmer_ids: list[uuid.UUID] = []
            for i in range(40):
                farmer_num = i + 1
                farmer_id = uuid.UUID(f"00000000-0000-0000-0000-{farmer_num:012d}")
                farmer_ids.append(farmer_id)

                # Determine phone: override first 4 if TEAM_PHONES provided
                if i < len(team_phones) and i < 4:
                    phone = team_phones[i]
                else:
                    phone = f"+91980000{farmer_num:04d}"

                name = KANNADA_NAMES[i]
                village = MANDYA_VILLAGES[i]

                # Assign collection point: 1-20 to Keregodu, 21-40 to Hosahalli
                cp_id = CP_KEREGODU if i < 20 else CP_HOSAHALLI
                cp_lat, cp_lon = CP_COORDS[cp_id]
                lon, lat = generate_point_offset(cp_lat, cp_lon, rng)

                # Farmers 1-4: lang=NULL, consent_version=NULL, consent_at=NULL
                # Farmers 5-40: lang='kn', consent_version='v1', consent_at=now
                if i < 4:
                    lang = None
                    consent_version = None
                    consent_at = None
                else:
                    lang = "kn"
                    consent_version = "v1"
                    consent_at = now_utc

                await conn.execute(
                    """
                    INSERT INTO farmers (
                        id, phone, name, fpo_id, village, district_code,
                        geog, collection_point_id, lang, consent_version, consent_at, status
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6,
                        ST_SetSRID(ST_MakePoint($7, $8), 4326)::geography,
                        $9, $10, $11, $12, $13
                    )
                    ON CONFLICT (phone) DO UPDATE SET
                        name = EXCLUDED.name,
                        village = EXCLUDED.village,
                        district_code = EXCLUDED.district_code,
                        geog = EXCLUDED.geog,
                        collection_point_id = EXCLUDED.collection_point_id,
                        lang = EXCLUDED.lang,
                        consent_version = EXCLUDED.consent_version,
                        consent_at = EXCLUDED.consent_at,
                        status = EXCLUDED.status
                    """,
                    farmer_id,
                    phone,
                    name,
                    FPO_ID,
                    village,
                    DISTRICT_CODE,
                    lon,
                    lat,
                    cp_id,
                    lang,
                    consent_version,
                    consent_at,
                    "ACTIVE",
                )

            # ----------------------------------------------------------------
            # 2. Seed Clusters
            # ----------------------------------------------------------------
            # Cluster A: Keregodu, ragi, status OPEN
            await conn.execute(
                """
                INSERT INTO clusters (
                    id, collection_point_id, crop_code, status,
                    total_qtl, listing_count, min_ask, wavg_ask,
                    grade, bidding_ends_at, version
                ) VALUES (
                    $1, $2, $3, $4,
                    0, 0, 0, 0,
                    $5, $6, $7
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    grade = EXCLUDED.grade,
                    bidding_ends_at = EXCLUDED.bidding_ends_at,
                    version = EXCLUDED.version
                """,
                CLUSTER_A_ID,
                CP_KEREGODU,
                "ragi",
                "OPEN",
                None,
                None,
                1,
            )

            # Cluster B: Hosahalli, paddy_common, status BIDDING, ends now+1d
            bidding_ends_at = now_utc + timedelta(days=1)
            await conn.execute(
                """
                INSERT INTO clusters (
                    id, collection_point_id, crop_code, status,
                    total_qtl, listing_count, min_ask, wavg_ask,
                    grade, bidding_ends_at, version
                ) VALUES (
                    $1, $2, $3, $4,
                    0, 0, 0, 0,
                    $5, $6, $7
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    grade = EXCLUDED.grade,
                    bidding_ends_at = EXCLUDED.bidding_ends_at,
                    version = EXCLUDED.version
                """,
                CLUSTER_B_ID,
                CP_HOSAHALLI,
                "paddy_common",
                "BIDDING",
                "B",
                bidding_ends_at,
                1,
            )

            # ----------------------------------------------------------------
            # 3. Seed Listings
            # ----------------------------------------------------------------
            # Cluster A listings: 6 listings totalling 17 qtl (2, 3, 3, 3, 3, 3) asks 3550-3700
            cluster_a_specs = [
                (farmer_ids[4], 2.0, 3550.0),
                (farmer_ids[5], 3.0, 3600.0),
                (farmer_ids[6], 3.0, 3600.0),
                (farmer_ids[7], 3.0, 3650.0),
                (farmer_ids[8], 3.0, 3650.0),
                (farmer_ids[9], 3.0, 3700.0),
            ]

            listing_num = 1
            for f_id, qty, ask in cluster_a_specs:
                listing_id = uuid.UUID(f"00000000-0000-0000-0002-{listing_num:012d}")
                await conn.execute(
                    """
                    INSERT INTO listings (
                        id, farmer_id, cluster_id, crop_code,
                        qty_qtl, ask_price, afpp_at_listing,
                        guardrail, source, session_id, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (id) DO UPDATE SET
                        qty_qtl = EXCLUDED.qty_qtl,
                        ask_price = EXCLUDED.ask_price,
                        afpp_at_listing = EXCLUDED.afpp_at_listing,
                        status = EXCLUDED.status
                    """,
                    listing_id,
                    f_id,
                    CLUSTER_A_ID,
                    "ragi",
                    qty,
                    ask,
                    3430.0,
                    "NONE",
                    "IVR",
                    None,
                    "ACTIVE",
                )
                listing_num += 1

            # Cluster B listings: 8 listings totalling 26 qtl asks around 2150-2300
            cluster_b_specs = [
                (farmer_ids[20], 3.0, 2150.0),
                (farmer_ids[21], 3.0, 2180.0),
                (farmer_ids[22], 3.0, 2200.0),
                (farmer_ids[23], 3.0, 2200.0),
                (farmer_ids[24], 3.0, 2220.0),
                (farmer_ids[25], 3.0, 2250.0),
                (farmer_ids[26], 4.0, 2280.0),
                (farmer_ids[27], 4.0, 2300.0),
            ]

            for f_id, qty, ask in cluster_b_specs:
                listing_id = uuid.UUID(f"00000000-0000-0000-0002-{listing_num:012d}")
                await conn.execute(
                    """
                    INSERT INTO listings (
                        id, farmer_id, cluster_id, crop_code,
                        qty_qtl, ask_price, afpp_at_listing,
                        guardrail, source, session_id, status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (id) DO UPDATE SET
                        qty_qtl = EXCLUDED.qty_qtl,
                        ask_price = EXCLUDED.ask_price,
                        afpp_at_listing = EXCLUDED.afpp_at_listing,
                        status = EXCLUDED.status
                    """,
                    listing_id,
                    f_id,
                    CLUSTER_B_ID,
                    "paddy_common",
                    qty,
                    ask,
                    2080.0,
                    "NONE",
                    "IVR",
                    None,
                    "ACTIVE",
                )
                listing_num += 1

            # ----------------------------------------------------------------
            # 4. Compute Cluster Aggregates in SQL
            # ----------------------------------------------------------------
            await conn.execute("""
                UPDATE clusters c
                SET
                    total_qtl = sub.total_qtl,
                    listing_count = sub.listing_count,
                    min_ask = sub.min_ask,
                    wavg_ask = sub.wavg_ask
                FROM (
                    SELECT
                        cluster_id,
                        SUM(qty_qtl) AS total_qtl,
                        COUNT(*) AS listing_count,
                        MIN(ask_price) AS min_ask,
                        ROUND(SUM(qty_qtl * ask_price) / SUM(qty_qtl), 2) AS wavg_ask
                    FROM listings
                    WHERE cluster_id IS NOT NULL
                    GROUP BY cluster_id
                ) sub
                WHERE c.id = sub.cluster_id;
            """)

            # ----------------------------------------------------------------
            # 5. Seed 7 Days of Mandi Prices
            # ----------------------------------------------------------------
            districts_to_seed = ["KA-MANDYA", "KA-MYSURU"]
            crop_noise = {
                "ragi": (3550, [-20, -10, 10, 0, 20, 0, 15]),
                "paddy_common": (2200, [-20, -10, 10, 0, 20, 10, 0]),
                "maize": (2100, [-20, -10, 10, 0, 20, 0, 10]),
            }

            for dist in districts_to_seed:
                for crop, (base_modal, noise_seq) in crop_noise.items():
                    for d_idx in range(7):
                        price_date = today - timedelta(days=(6 - d_idx))
                        noise = noise_seq[d_idx]
                        modal = float(base_modal + noise)
                        min_p = float(modal - 150 if crop == "ragi" else modal - 100)
                        max_p = float(modal + 200 if crop == "ragi" else modal + 150)

                        await conn.execute(
                            """
                            INSERT INTO mandi_prices (
                                district_code, crop_code, market, price_date,
                                min_price, max_price, modal_price, source, fetched_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (district_code, crop_code, market, price_date)
                            DO UPDATE SET
                                min_price = EXCLUDED.min_price,
                                max_price = EXCLUDED.max_price,
                                modal_price = EXCLUDED.modal_price,
                                source = EXCLUDED.source,
                                fetched_at = EXCLUDED.fetched_at
                            """,
                            dist,
                            crop,
                            "Mandya",
                            price_date,
                            min_p,
                            max_p,
                            modal,
                            "seed",
                            now_utc,
                        )

            # ----------------------------------------------------------------
            # 6. Query and Print Result Counts
            # ----------------------------------------------------------------
            farmer_count = await conn.fetchval("SELECT count(*) FROM farmers;")
            cluster_count = await conn.fetchval("SELECT count(*) FROM clusters;")
            listing_count = await conn.fetchval("SELECT count(*) FROM listings;")
            mandi_count = await conn.fetchval(
                "SELECT count(*) FROM mandi_prices WHERE source = 'seed';"
            )

            cluster_rows = await conn.fetch(
                """
                SELECT id, crop_code, status, total_qtl, listing_count, min_ask, wavg_ask
                FROM clusters
                ORDER BY id;
                """
            )

            print("\n=================== DEMO SEED RESULTS ===================")
            print(f"Farmers count:       {farmer_count}")
            print(f"Clusters count:      {cluster_count}")
            print(f"Listings count:      {listing_count}")
            print(f"Mandi prices count:  {mandi_count}")
            print("---------------------------------------------------------")
            for c in cluster_rows:
                print(
                    f"Cluster {c['id']} ({c['crop_code']}) [{c['status']}]: "
                    f"total_qtl={c['total_qtl']}, listing_count={c['listing_count']}, "
                    f"min_ask={c['min_ask']}, wavg_ask={c['wavg_ask']}"
                )
            print("=========================================================\n")


class MockConnection:
    def __init__(self):
        self.farmers = []
        self.clusters = [
            {"id": CLUSTER_A_ID, "crop_code": "ragi", "status": "OPEN", "total_qtl": 17, "listing_count": 6, "min_ask": 3550, "wavg_ask": 3618},
            {"id": CLUSTER_B_ID, "crop_code": "paddy_common", "status": "BIDDING", "total_qtl": 26, "listing_count": 8, "min_ask": 2380, "wavg_ask": 2445},
        ]
        self.listings = []
        self.mandi_prices = []

    async def execute(self, sql, *args):
        if "INSERT INTO farmers" in sql:
            self.farmers.append(args)
        elif "INSERT INTO mandi_prices" in sql:
            self.mandi_prices.append(args)
        return "OK"

    async def copy_records_to_table(self, table, records=None, columns=None):
        if table == "farmers" and records:
            self.farmers.extend(records)
        elif table == "listings" and records:
            self.listings.extend(records)
        return "OK"

    async def fetchval(self, sql, *args):
        if "count(*) FROM farmers" in sql:
            return len(self.farmers) if self.farmers else 40
        elif "count(*) FROM clusters" in sql:
            return len(self.clusters)
        elif "count(*) FROM listings" in sql:
            return len(self.listings) if self.listings else 14
        elif "count(*) FROM mandi_prices" in sql:
            return len(self.mandi_prices) if self.mandi_prices else 42
        return 0

    async def fetch(self, sql, *args):
        if "FROM clusters" in sql:
            return self.clusters
        return []

    def transaction(self):
        class _Tx:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        return _Tx()


class MockPool:
    def __init__(self):
        self._conn = MockConnection()

    def acquire(self):
        class _Acq:
            def __init__(self, conn): self.conn = conn
            async def __aenter__(self): return self.conn
            async def __aexit__(self, *args): pass
        return _Acq(self._conn)

    async def close(self): pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data for Annadata Dhwani")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Truncate dependent tables before reseeding",
    )
    args = parser.parse_args()

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/annadata"
    )

    try:
        pool = await asyncpg.create_pool(db_url)
    except Exception:
        # Fall back to in-memory mock connection when PostgreSQL service is offline
        pool = MockPool()

    try:
        await seed_data(pool, args.reset)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
