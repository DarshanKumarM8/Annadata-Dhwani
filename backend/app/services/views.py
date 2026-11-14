"""JSON shapes shared by REST and WebSocket events (contract C4/C5). Owner: Darshan.

No farmer phone number or name ever leaves this module: lots are anonymous (lot number, quantity, ask).
"""
import json

from .. import cache, db

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
        else:                       # event payload: the WebSocket hub turns buyer_id into a per-viewer "mine"
            best["buyer_id"] = str(r["best_buyer"])
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


async def cluster_list(conn, statuses=None, crop=None, buyer_id=None, fpo_id=None) -> list[dict]:
    rows = await conn.fetch(CLUSTER_SQL + """ WHERE ($1::text[] IS NULL OR c.status = ANY($1))
                                              AND ($2::text IS NULL OR c.crop_code = $2)
                                              AND ($3::uuid IS NULL OR cp.fpo_id = $3) ORDER BY c.code""",
                            statuses, crop, fpo_id)
    return [shape(r, buyer_id) for r in rows]


async def price_reference(district_code: str, crop_code: str) -> dict | None:
    """Mandi reference for a district and crop, by CODE ('KA-MANDYA', 'ragi'). In order: the cached/stored price floor (today, or the
    last 7 days); else computed on the spot from the newest mandi price and the district's deduction rule. None only when the
    database holds no mandi price for that crop at all."""
    from . import pricing
    floor = await pricing.get_floor(db.pool, cache.redis, district_code, crop_code)
    if floor:
        return floor
    rows = await db.pool.fetch("""SELECT modal_price, price_date FROM mandi_prices WHERE district_code = $1 AND crop_code = $2
                                  AND price_date = (SELECT max(price_date) FROM mandi_prices
                                                    WHERE district_code = $1 AND crop_code = $2)""", district_code, crop_code)
    if not rows:
        return None
    modals = [float(r["modal_price"]) for r in rows]
    modal = pricing.safe_median(pricing.filter_outliers(modals)) or pricing.safe_median(modals)
    rule = await db.pool.fetchrow("SELECT transport_per_qtl, handling_per_qtl, pct_deduction FROM deduction_rules WHERE district_code = $1",
                                  district_code)
    transport, handling, pct = ((float(rule["transport_per_qtl"]), float(rule["handling_per_qtl"]), float(rule["pct_deduction"]))
                                if rule else (50.0, 10.0, 0.02))
    age = (pricing.today_ist() - rows[0]["price_date"]).days
    return {"modal_price": modal, "afpp": pricing.compute_afpp(modal, pct, transport, handling),
            "basis": "DISTRICT_FRESH" if age <= 1 else ("DISTRICT_7D" if age <= 7 else "STALE"),
            "price_date": rows[0]["price_date"].isoformat()}


async def cluster_detail(conn, cluster_id, buyer_id=None) -> dict | None:
    base = await cluster_view(conn, cluster_id, buyer_id)
    if not base:
        return None
    lots = await conn.fetch("""SELECT qty_qtl, ask_price FROM listings l
                               WHERE l.cluster_id = $1::uuid AND l.status IN ('ACTIVE','ACCEPTED','SOLD')
                               ORDER BY l.ask_price, l.created_at""", base["id"])
    msp = await conn.fetchval("SELECT msp FROM crops WHERE code = $1", base["crop_code"])
    district = await conn.fetchval("""SELECT cp.district_code FROM clusters c
                                      JOIN collection_points cp ON cp.id = c.collection_point_id WHERE c.id = $1::uuid""", base["id"])
    price_ref = await price_reference(district, base["crop_code"])
    return {**base,
            "lots": [{"lot_no": i + 1, "qty_qtl": float(x["qty_qtl"]), "ask_price": float(x["ask_price"])}
                     for i, x in enumerate(lots)],
            "price_ref": price_ref, "msp": _f(msp)}
