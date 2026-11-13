"""JSON shapes shared by REST and WebSocket events (contract C4/C5). Owner: Darshan.

No farmer phone number or name ever leaves this module: lots are anonymous (lot number, quantity, ask).
"""
import json

from .. import cache

CLUSTER_SQL = """
SELECT c.id::text AS id, c.code, c.crop_code, cr.name_en AS crop_name, d.name AS district,
       cp.name AS cp_name, ST_Y(cp.geog::geometry) AS lat, ST_X(cp.geog::geometry) AS lon,
       c.status, c.total_qtl, c.listing_count, c.min_ask, c.wavg_ask, c.grade, c.bidding_ends_at,
       c.version, c.best_bid_id, b.price_per_qtl AS best_price, b.buyer_id AS best_buyer,
       (SELECT '/media/v/' || regexp_replace(v.photo_path, '^.*[/\\\\]', '')
          FROM verifications v WHERE v.cluster_id = c.id) AS photo_url
FROM clusters c
JOIN crops cr ON cr.code = c.crop_code
JOIN collection_points cp ON cp.id = c.collection_point_id
JOIN districts d ON d.code = cp.district_code
LEFT JOIN bids b ON b.id = c.best_bid_id
"""


def _f(x):
    return None if x is None else float(x)


def shape(r, buyer_id=None) -> dict:
    best = None
    if r["best_price"] is not None:
        best = {"price_per_qtl": float(r["best_price"])}
        if buyer_id is not None:
            best["mine"] = str(r["best_buyer"]) == str(buyer_id)
    return {"id": r["id"], "code": r["code"], "crop_code": r["crop_code"], "crop_name": r["crop_name"],
            "district": r["district"],
            "collection_point": {"name": r["cp_name"], "lat": r["lat"], "lon": r["lon"]},
            "status": r["status"], "total_qtl": _f(r["total_qtl"]), "listing_count": r["listing_count"],
            "min_ask": _f(r["min_ask"]), "wavg_ask": _f(r["wavg_ask"]), "grade": r["grade"],
            "photo_url": r["photo_url"],
            "bidding_ends_at": r["bidding_ends_at"].isoformat() if r["bidding_ends_at"] else None,
            "best_bid": best, "version": r["version"]}


async def cluster_view(conn, cluster_id, buyer_id=None) -> dict | None:
    r = await conn.fetchrow(CLUSTER_SQL + " WHERE c.id = $1::uuid", str(cluster_id))
    return shape(r, buyer_id) if r else None


async def cluster_list(conn, statuses=None, crop=None, buyer_id=None) -> list[dict]:
    rows = await conn.fetch(CLUSTER_SQL + """ WHERE ($1::text[] IS NULL OR c.status = ANY($1))
                                              AND ($2::text IS NULL OR c.crop_code = $2) ORDER BY c.code""",
                            statuses, crop)
    return [shape(r, buyer_id) for r in rows]


async def cluster_detail(conn, cluster_id, buyer_id=None) -> dict | None:
    base = await cluster_view(conn, cluster_id, buyer_id)
    if not base:
        return None
    lots = await conn.fetch("""SELECT qty_qtl, ask_price, district_code FROM listings l
                               JOIN farmers f ON f.id = l.farmer_id
                               WHERE l.cluster_id = $1::uuid AND l.status IN ('ACTIVE','ACCEPTED','SOLD')
                               ORDER BY l.ask_price, l.created_at""", base["id"])
    msp = await conn.fetchval("SELECT msp FROM crops WHERE code = $1", base["crop_code"])
    price_ref = None
    if lots:
        raw = await cache.redis.get(f"floor:{lots[0]['district_code']}:{base['crop_code']}")
        price_ref = json.loads(raw) if raw else None
    return {**base,
            "lots": [{"lot_no": i + 1, "qty_qtl": float(x["qty_qtl"]), "ask_price": float(x["ask_price"])}
                     for i, x in enumerate(lots)],
            "price_ref": price_ref, "msp": _f(msp)}
