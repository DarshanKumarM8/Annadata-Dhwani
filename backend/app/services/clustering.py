"""Clustering. Owner: Darshan.

Cluster key is (collection_point_id, crop_code). Every join for one key is serialised by a transaction-scoped advisory
lock, and a partial unique index (clusters_one_joinable) is the backstop, so 50 simultaneous commits make ONE cluster
with the right total. A cluster turns READY at READY_QTL quintals and an agent VERIFY task is announced in the same
transaction as the change; events are published after commit.
"""
import uuid

from ..engine.engine import ListingExists
from . import events, views

READY_QTL = 20


async def recompute_cluster(conn, cluster_id) -> None:
    """The ONLY writer of cluster totals."""
    await conn.execute("""
        UPDATE clusters c SET
          total_qtl = COALESCE(a.q, 0), listing_count = COALESCE(a.n, 0),
          min_ask = a.mn, wavg_ask = a.wavg, version = c.version + 1, updated_at = now()
        FROM (SELECT SUM(qty_qtl) q, COUNT(*) n, MIN(ask_price) mn,
                     ROUND(SUM(qty_qtl * ask_price) / NULLIF(SUM(qty_qtl), 0), 2) wavg
              FROM listings WHERE cluster_id = $1 AND status = 'ACTIVE') a
        WHERE c.id = $1""", cluster_id)


async def _become_ready(conn, cluster_id) -> bool:
    """OPEN -> READY once the total reaches READY_QTL. Returns True if this call made the change."""
    n = await conn.fetchval("""UPDATE clusters SET status = 'READY', version = version + 1, updated_at = now()
                               WHERE id = $1 AND status = 'OPEN' AND total_qtl >= $2 RETURNING 1""",
                            cluster_id, READY_QTL)
    return bool(n)


async def commit_listing(pool, s: dict) -> int:
    """Create (or return) the listing for this call session. Idempotent on session id. Returns the listing code."""
    d = s["data"]
    sid = uuid.UUID(s["id"])
    seqs: list[int] = []
    async with pool.acquire() as conn, conn.transaction():
        f = await conn.fetchrow("SELECT collection_point_id FROM farmers WHERE id = $1", s["farmer_id"])
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                           f"{f['collection_point_id']}:{d['crop']}")
        # listings.session_id references call_sessions: write a minimal row (the checkpoint keeps it current)
        await conn.execute("""
            INSERT INTO call_sessions (id, phone, farmer_id, kind, provider, provider_call_id, state, data, version)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data, updated_at = now()""",
            sid,
            s["phone"], s["farmer_id"], s["kind"], s["provider"], s["call_id"], s["state"], d, s["version"])
        done = await conn.fetchrow("SELECT code FROM listings WHERE session_id = $1", sid)
        if done:
            return done["code"]
        if await conn.fetchval("""SELECT 1 FROM listings WHERE farmer_id = $1 AND crop_code = $2
                                  AND status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED')""", s["farmer_id"], d["crop"]):
            raise ListingExists()
        cluster_id = await conn.fetchval("""
            SELECT id FROM clusters WHERE collection_point_id = $1 AND crop_code = $2
            AND status IN ('OPEN','READY')""", f["collection_point_id"], d["crop"])
        if not cluster_id:
            cluster_id = await conn.fetchval(
                "INSERT INTO clusters (collection_point_id, crop_code) VALUES ($1, $2) RETURNING id",
                f["collection_point_id"], d["crop"])
        floor = d.get("floor")
        row = await conn.fetchrow("""
            INSERT INTO listings (farmer_id, cluster_id, crop_code, qty_qtl, ask_price, afpp_at_listing,
                                  guardrail, source, session_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'IVR', $8) RETURNING code, qty_qtl, ask_price""",
            s["farmer_id"], cluster_id, d["crop"], d["qty"], d["price"],
            floor["afpp"] if floor else None, d.get("guardrail", "NONE"), sid)
        await recompute_cluster(conn, cluster_id)
        became_ready = await _become_ready(conn, cluster_id)
        # events, in the same transaction as the change
        seqs.append(await events.emit(conn, "listing.created", {
            "cluster_id": str(cluster_id), "crop_code": d["crop"], "qty_qtl": float(row["qty_qtl"]),
            "ask_price": float(row["ask_price"]), "source": "IVR"}))
        seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, cluster_id)))
        if became_ready:
            seqs.append(await events.emit(conn, "task.created", {"kind": "VERIFY", "ref_id": str(cluster_id)},
                                          "agent"))
        code = row["code"]
    await events.publish(seqs)                      # after commit
    return code
