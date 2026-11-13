"""Buyer bids and deals (contract C4). Owner: Darshan."""
from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from .. import db
from ..services import bidding, events
from .auth import ApiError, require

router = APIRouter(prefix="/api")


@router.post("/clusters/{cid}/bids")
async def place_bid(cid: str, body: dict, idempotency_key: str | None = Header(default=None),
                    who: dict = Depends(require("buyer"))):
    if not idempotency_key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED")
    if who["role"] == "admin":
        raise ApiError(403, "FORBIDDEN")
    try:
        bid, created = await bidding.place_bid(db.pool, who["sub"], cid, body.get("price_per_qtl"),
                                               body.get("min_qty_qtl"), idempotency_key)
    except ValueError:                                   # malformed cluster uuid
        raise ApiError(404, "NOT_FOUND")
    return JSONResponse(bid, status_code=201 if created else 200)


@router.get("/bids/mine")
async def bids_mine(who: dict = Depends(require("buyer"))):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("""SELECT id, cluster_id::text, price_per_qtl, min_qty_qtl, status
                                   FROM bids WHERE buyer_id = $1::uuid ORDER BY created_at DESC""", who["sub"])
        out = []
        for r in rows:
            prog = await bidding._progress(conn, r["id"]) if r["status"] in ("CONFIRMING", "DEAL", "FAILED") else None
            out.append({"id": str(r["id"]), "cluster_id": r["cluster_id"], "price_per_qtl": float(r["price_per_qtl"]),
                        "min_qty_qtl": float(r["min_qty_qtl"]), "status": r["status"], "progress": prog})
    return {"bids": out}


@router.get("/deals/mine")
async def deals_mine(who: dict = Depends(require("buyer"))):
    rows = await db.pool.fetch("""
        SELECT d.id::text, d.cluster_id::text, d.qty_qtl, d.price_per_qtl, d.gross_value, d.platform_fee, d.status,
               d.pickup_by, d.payment_ref, f.name AS fpo_name, f.payee_details
        FROM deals d JOIN clusters c ON c.id = d.cluster_id
        JOIN collection_points cp ON cp.id = c.collection_point_id JOIN fpos f ON f.id = cp.fpo_id
        WHERE d.buyer_id = $1::uuid ORDER BY d.created_at DESC""", who["sub"])
    return {"deals": [{"id": r["id"], "cluster_id": r["cluster_id"], "qty_qtl": float(r["qty_qtl"]),
                       "price_per_qtl": float(r["price_per_qtl"]), "gross_value": float(r["gross_value"]),
                       "platform_fee": float(r["platform_fee"]), "status": r["status"],
                       "pickup_by": r["pickup_by"].isoformat(), "payment_ref": r["payment_ref"],
                       "fpo": {"name": r["fpo_name"], "payee_details": r["payee_details"]}} for r in rows]}


@router.post("/deals/{did}/payment-reported")
async def payment_reported(did: str, body: dict, who: dict = Depends(require("buyer"))):
    ref = str(body.get("payment_ref", "")).strip()
    if not ref:
        raise ApiError(422, "PAYMENT_REF_REQUIRED")
    try:
        async with db.pool.acquire() as conn, conn.transaction():
            d = await conn.fetchrow("""UPDATE deals SET status = 'PAYMENT_REPORTED', payment_ref = $3, updated_at = now()
                                       WHERE id = $1::uuid AND buyer_id = $2::uuid AND status = 'CONFIRMED'
                                       RETURNING id::text""", did, who["sub"], ref[:60])
            if not d:
                cur = await conn.fetchval("SELECT status FROM deals WHERE id = $1::uuid AND buyer_id = $2::uuid",
                                          did, who["sub"])
                if cur is None:
                    raise ApiError(404, "NOT_FOUND")
                return {"status": cur}                  # already reported: idempotent
            s1 = await events.emit(conn, "deal.updated", {"deal_id": did, "status": "PAYMENT_REPORTED",
                                                          "for_buyer": who["sub"]}, "buyer")
            s2 = await events.emit(conn, "deal.updated", {"deal_id": did, "status": "PAYMENT_REPORTED"}, "agent")
    except (ValueError, __import__("asyncpg").DataError):
        raise ApiError(404, "NOT_FOUND")
    await events.publish([s1, s2])
    return {"status": "PAYMENT_REPORTED"}
