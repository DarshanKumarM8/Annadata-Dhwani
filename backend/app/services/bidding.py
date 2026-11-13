"""Ascending auction, confirmation round and deal creation. Owner: Darshan.

Lock order (to avoid deadlocks with commit_listing): advisory lock for (collection point, crop) FIRST, then the cluster row.
Events are written in the same transaction as the change and published after commit.

Confirmation round: each listing in the winning cluster gets a bid_responses row. Responses arrive from the BID_OFFER
call (record_response) or, in the demo, from simulate_farmers(). A round resolves when nothing is PENDING or at
confirm_deadline (PENDING then counts as NO_ANSWER). accepted qty >= min_qty -> deal; else the bid FAILS and the
cluster returns to BIDDING once, then NO_BID.
"""
import asyncio
import logging
from datetime import timedelta
from decimal import Decimal

import asyncpg

from .. import db
from ..api.auth import ApiError
from ..config import settings
from . import clustering, events, jobs, views

log = logging.getLogger("bidding")
MIN_STEP = Decimal(10)
FEE_RATE = Decimal("0.015")


def _bid(r) -> dict:
    return {"id": str(r["id"]), "status": r["status"], "price_per_qtl": float(r["price_per_qtl"]),
            "min_qty_qtl": float(r["min_qty_qtl"])}


async def place_bid(pool, buyer_id: str, cluster_id: str, price, min_qty, key: str) -> tuple[dict, bool]:
    """Returns (bid, created). A repeated Idempotency-Key returns the original bid with created=False."""
    try:
        price, min_qty = Decimal(str(price)), Decimal(str(min_qty))
    except Exception:
        raise ApiError(422, "BAD_NUMBER")
    if price <= 0:
        raise ApiError(422, "BAD_NUMBER")
    seqs: list[int] = []
    try:
        async with pool.acquire() as conn, conn.transaction():
            prior = await conn.fetchrow("SELECT * FROM bids WHERE buyer_id = $1::uuid AND idempotency_key = $2",
                                        buyer_id, key)
            if prior:
                return _bid(prior), False
            # lock the row FIRST; reading the best bid in a separate statement sees the committed winner
            # (a join in the locking statement would keep the pre-wait snapshot of the bids row)
            c = await conn.fetchrow("""SELECT id, status, total_qtl, min_ask, best_bid_id FROM clusters
                                       WHERE id = $1::uuid FOR UPDATE""", cluster_id)
            if c:
                c = dict(c)
                c["best"] = (await conn.fetchval("SELECT price_per_qtl FROM bids WHERE id = $1", c["best_bid_id"])
                             if c["best_bid_id"] else None)
            if not c:
                raise ApiError(404, "NOT_FOUND")
            if c["status"] != "BIDDING":
                raise ApiError(409, "CLUSTER_NOT_BIDDING")
            floor = max(c["min_ask"] or 0, (c["best"] + MIN_STEP) if c["best"] is not None else 0)
            if price < floor:
                raise ApiError(409, "BID_TOO_LOW", min_next=float(floor))
            if min_qty <= 0 or min_qty > c["total_qtl"]:
                raise ApiError(422, "MIN_QTY_TOO_HIGH")
            if c["best_bid_id"]:
                await conn.execute("UPDATE bids SET status = 'OUTBID' WHERE id = $1", c["best_bid_id"])
            bid = await conn.fetchrow("""INSERT INTO bids (cluster_id, buyer_id, price_per_qtl, min_qty_qtl, idempotency_key)
                                         VALUES ($1, $2::uuid, $3, $4, $5) RETURNING *""",
                                      c["id"], buyer_id, price, min_qty, key)
            await conn.execute("""UPDATE clusters SET best_bid_id = $2, version = version + 1, updated_at = now()
                                  WHERE id = $1""", c["id"], bid["id"])
            seqs.append(await events.emit(conn, "bid.placed", {
                "cluster_id": str(c["id"]), "bid_id": str(bid["id"]), "price_per_qtl": float(price),
                "buyer_id": buyer_id}, "buyer"))
            seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, c["id"])))
    except asyncpg.UniqueViolationError:                 # same key raced in: return the winner's bid
        prior = await pool.fetchrow("SELECT * FROM bids WHERE buyer_id = $1::uuid AND idempotency_key = $2",
                                    buyer_id, key)
        if prior:
            return _bid(prior), False
        raise
    await events.publish(seqs)
    return _bid(bid), True


async def _progress(conn, bid_id) -> dict:
    t = await conn.fetchrow("""SELECT
        COALESCE(sum(l.qty_qtl) FILTER (WHERE r.response = 'ACCEPT'), 0) AS a,
        COALESCE(sum(l.qty_qtl) FILTER (WHERE r.response IN ('REJECT','NO_ANSWER')), 0) AS r,
        COALESCE(sum(l.qty_qtl) FILTER (WHERE r.response = 'PENDING'), 0) AS p
        FROM bid_responses r JOIN listings l ON l.id = r.listing_id WHERE r.bid_id = $1""", bid_id)
    return {"accepted_qtl": float(t["a"]), "rejected_qtl": float(t["r"]), "pending_qtl": float(t["p"])}


async def _locked_cluster(conn, cluster_id):
    """Advisory lock first (same key as commit_listing), then the row."""
    k = await conn.fetchrow("SELECT collection_point_id, crop_code FROM clusters WHERE id = $1::uuid", cluster_id)
    if not k:
        return None
    await clustering.lock_key(conn, k["collection_point_id"], k["crop_code"])
    return await conn.fetchrow("SELECT * FROM clusters WHERE id = $1::uuid FOR UPDATE", cluster_id)


async def close_auction(pool, cluster_id: str) -> str | None:
    """End the bidding window. Returns the cluster's new status, or None if it does not exist."""
    seqs: list[int] = []
    async with pool.acquire() as conn, conn.transaction():
        c = await _locked_cluster(conn, cluster_id)
        if not c:
            return None
        if c["status"] != "BIDDING":
            return c["status"]
        if not c["best_bid_id"]:
            await conn.execute("UPDATE clusters SET status = 'NO_BID', version = version + 1, updated_at = now() "
                               "WHERE id = $1", c["id"])
            status = "NO_BID"
        else:
            await conn.execute("UPDATE bids SET status = 'CONFIRMING', confirm_deadline = now() + $2 WHERE id = $1",
                               c["best_bid_id"], timedelta(seconds=settings.confirm_s))
            await conn.execute("UPDATE clusters SET status = 'CONFIRMING', version = version + 1, updated_at = now() "
                               "WHERE id = $1", c["id"])
            await conn.execute("""INSERT INTO bid_responses (bid_id, listing_id)
                                  SELECT $1, id FROM listings WHERE cluster_id = $2 AND status = 'ACTIVE'
                                  ON CONFLICT DO NOTHING""", c["best_bid_id"], c["id"])
            await jobs.enqueue_bid_offers(conn, c["best_bid_id"], c["id"])        # one call per lot
            buyer = await conn.fetchval("SELECT buyer_id::text FROM bids WHERE id = $1", c["best_bid_id"])
            seqs.append(await events.emit(conn, "bid.confirming", {
                "cluster_id": str(c["id"]), "bid_id": str(c["best_bid_id"]), "for_buyer": buyer,
                **await _progress(conn, c["best_bid_id"])}, "buyer"))
            status = "CONFIRMING"
        seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, c["id"])))
    await events.publish(seqs)
    return status


async def record_response(pool, bid_id: str, listing_id: str, response: str) -> bool:
    """First answer wins; a repeat is a no-op. Returns True if this call recorded it."""
    n = await pool.execute("""UPDATE bid_responses SET response = $3, responded_at = now()
                              WHERE bid_id = $1::uuid AND listing_id = $2::uuid AND response = 'PENDING'""",
                           bid_id, listing_id, response)
    if n == "UPDATE 1":
        await resolve_round(pool, bid_id)
        return True
    return False


async def resolve_round(pool, bid_id: str, deadline_passed: bool = False) -> str:
    """Progress the round, or settle it. Returns 'WAITING' | 'DEAL' | 'FAILED' | 'IGNORED'."""
    seqs: list[int] = []
    async with pool.acquire() as conn, conn.transaction():
        b = await conn.fetchrow("SELECT * FROM bids WHERE id = $1::uuid", bid_id)
        if not b:
            return "IGNORED"
        c = await _locked_cluster(conn, b["cluster_id"])
        if c["status"] != "CONFIRMING" or str(c["best_bid_id"]) != str(b["id"]):
            return "IGNORED"
        pend = await conn.fetchval("SELECT count(*) FROM bid_responses WHERE bid_id = $1 AND response = 'PENDING'",
                                   b["id"])
        if pend and not deadline_passed:
            seqs.append(await events.emit(conn, "bid.confirming", {
                "cluster_id": str(c["id"]), "bid_id": str(b["id"]), "for_buyer": str(b["buyer_id"]),
                **await _progress(conn, b["id"])}, "buyer"))
            outcome = "WAITING"
        else:
            await conn.execute("""UPDATE bid_responses SET response = 'NO_ANSWER' WHERE bid_id = $1
                                  AND response = 'PENDING'""", b["id"])
            prog = await _progress(conn, b["id"])
            await jobs.cancel_for_bid(conn, b["id"])                  # stop calling farmers for a settled round
            if Decimal(str(prog["accepted_qtl"])) >= b["min_qty_qtl"] and prog["accepted_qtl"] > 0:
                outcome = await _make_deal(conn, c, b, prog, seqs)
            else:
                outcome = await _fail_round(conn, c, b, seqs)
    await events.publish(seqs)
    return outcome


async def _make_deal(conn, c, b, prog, seqs) -> str:
    qty = Decimal(str(prog["accepted_qtl"]))
    gross = qty * b["price_per_qtl"]
    deal = await conn.fetchrow("""
        INSERT INTO deals (cluster_id, bid_id, buyer_id, qty_qtl, price_per_qtl, gross_value, platform_fee, pickup_by)
        VALUES ($1, $2, $3, $4, $5, $6::numeric, round($6::numeric * $7::numeric, 2), current_date + 3) RETURNING *""",
                               c["id"], b["id"], b["buyer_id"], qty, b["price_per_qtl"], gross, FEE_RATE)
    await conn.execute("""UPDATE listings SET status = 'ACCEPTED' WHERE id IN
                          (SELECT listing_id FROM bid_responses WHERE bid_id = $1 AND response = 'ACCEPT')""", b["id"])
    # lots that did not accept go back into the pool for their pickup point
    left = await conn.fetch("SELECT id FROM listings WHERE cluster_id = $1 AND status = 'ACTIVE'", c["id"])
    new_cluster = None
    if left:
        new_cluster = await clustering.join_cluster(conn, c["collection_point_id"], c["crop_code"])
        await conn.execute("UPDATE listings SET cluster_id = $2 WHERE cluster_id = $1 AND status = 'ACTIVE'",
                           c["id"], new_cluster)
    await conn.execute("UPDATE bids SET status = 'DEAL' WHERE id = $1", b["id"])
    await conn.execute("UPDATE clusters SET status = 'DEAL', version = version + 1, updated_at = now() WHERE id = $1",
                       c["id"])
    await clustering.recompute_cluster(conn, c["id"])
    payload = {"deal_id": str(deal["id"]), "cluster_id": str(c["id"]), "qty_qtl": float(qty),
               "price_per_qtl": float(b["price_per_qtl"]), "gross_value": float(gross),
               "platform_fee": float(deal["platform_fee"]), "pickup_by": deal["pickup_by"].isoformat()}
    seqs.append(await events.emit(conn, "deal.created", {**payload, "for_buyer": str(b["buyer_id"])}, "buyer"))
    seqs.append(await events.emit(conn, "deal.created", payload, "agent"))
    seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, c["id"])))
    if new_cluster:
        await clustering.recompute_cluster(conn, new_cluster)
        became = await clustering._become_ready(conn, new_cluster)
        seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, new_cluster)))
        if became:
            seqs.append(await events.emit(conn, "task.created", {"kind": "VERIFY", "ref_id": str(new_cluster)},
                                          "agent"))
    return "DEAL"


async def _fail_round(conn, c, b, seqs) -> str:
    await conn.execute("UPDATE bids SET status = 'FAILED' WHERE id = $1", b["id"])
    failed = await conn.fetchval("SELECT count(*) FROM bids WHERE cluster_id = $1 AND status = 'FAILED'", c["id"])
    if failed <= 1:
        await conn.execute("""UPDATE clusters SET status = 'BIDDING', best_bid_id = NULL, version = version + 1,
                              bidding_ends_at = now() + $2, updated_at = now() WHERE id = $1""",
                           c["id"], timedelta(seconds=settings.auction_s))
    else:
        await conn.execute("UPDATE clusters SET status = 'NO_BID', best_bid_id = NULL, version = version + 1, "
                           "updated_at = now() WHERE id = $1", c["id"])
    seqs.append(await events.emit(conn, "bid.failed", {
        "cluster_id": str(c["id"]), "bid_id": str(b["id"]), "for_buyer": str(b["buyer_id"])}, "buyer"))
    seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, c["id"])))
    return "FAILED"


async def simulate_farmers(pool, cluster_id: str, accept: bool = True, accepted_lots: int | None = None) -> dict:
    """DEMO ONLY: answer the confirmation round for the farmers (stands in for the BID_OFFER calls)."""
    rows = await pool.fetch("""SELECT r.bid_id::text, r.listing_id::text FROM bid_responses r
                               JOIN clusters c ON c.best_bid_id = r.bid_id
                               WHERE c.id = $1::uuid AND r.response = 'PENDING' ORDER BY r.id""", cluster_id)
    if not rows:
        return {"answered": 0}
    n = len(rows) if accepted_lots is None else accepted_lots
    for i, r in enumerate(rows):
        await pool.execute("""UPDATE bid_responses SET response = $3, responded_at = now()
                              WHERE bid_id = $1::uuid AND listing_id = $2::uuid AND response = 'PENDING'""",
                           r["bid_id"], r["listing_id"], "ACCEPT" if accept and i < n else "REJECT")
    return {"answered": len(rows), "outcome": await resolve_round(pool, rows[0]["bid_id"])}


async def tick(pool) -> None:
    """Scheduler pass: close due auctions, settle confirmation rounds past their deadline."""
    for r in await pool.fetch("SELECT id::text FROM clusters WHERE status = 'BIDDING' AND bidding_ends_at <= now()"):
        await close_auction(pool, r["id"])
    for r in await pool.fetch("""SELECT b.id::text FROM bids b JOIN clusters c ON c.best_bid_id = b.id
                                 WHERE b.status = 'CONFIRMING' AND c.status = 'CONFIRMING'
                                 AND b.confirm_deadline <= now()"""):
        await resolve_round(pool, r["id"], deadline_passed=True)


async def run(interval_s: float = 3) -> None:
    while True:
        try:
            await tick(db.pool)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler pass failed")
        await asyncio.sleep(interval_s)
