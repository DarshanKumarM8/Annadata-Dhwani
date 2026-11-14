"""FPO agent endpoints: login, tasks, verification, triage, payment confirmation (contract C4). Owner: Darshan."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .. import cache, db
from ..config import settings
from ..services import events, views
from .auth import ApiError, make_token, require

router = APIRouter(prefix="/api")
MAX_PHOTO = 2 * 1024 * 1024


@router.post("/auth/agent/login")
async def agent_login(body: dict):
    phone, pin = str(body.get("phone", "")).strip(), str(body.get("pin", ""))
    if not phone or not pin:
        return JSONResponse({"error": "BAD_CREDENTIALS"}, status_code=401)
    key = f"rl:login:{phone}"
    if int(await cache.redis.get(key) or 0) >= 5:
        return JSONResponse({"error": "LOCKED"}, status_code=429)
    a = await db.pool.fetchrow("SELECT id, name, fpo_id, pin_hash FROM agents WHERE phone = $1 AND active", phone)
    ok = bool(a) and await asyncio.to_thread(bcrypt.checkpw, pin.encode(), a["pin_hash"].encode())
    if not ok:
        if await cache.redis.incr(key) == 1:
            await cache.redis.expire(key, 900)
        return JSONResponse({"error": "BAD_CREDENTIALS"}, status_code=401)
    await cache.redis.delete(key)
    return {"token": make_token(str(a["id"]), "agent"),
            "agent": {"id": str(a["id"]), "name": a["name"], "fpo_id": str(a["fpo_id"])}}


async def _fpo(agent_id: str):
    f = await db.pool.fetchval("SELECT fpo_id FROM agents WHERE id = $1::uuid", agent_id)
    if not f:
        raise ApiError(403, "FORBIDDEN")
    return f


@router.get("/agent/tasks")
async def tasks(who: dict = Depends(require("agent"))):
    fpo = await _fpo(who["sub"])
    async with db.pool.acquire() as conn:
        verify = await views.cluster_list(conn, ["READY"], None, None, fpo)
        tickets = await conn.fetch("""
            SELECT t.id::text, COALESCE(f.village, 'Unknown') AS village,
                   COALESCE(split_part(f.name, ' ', 1), 'Caller') AS first_name, t.reason, t.status, t.created_at
            FROM triage_tickets t LEFT JOIN farmers f ON f.id = t.farmer_id
            WHERE t.status IN ('OPEN','ASSIGNED') AND (f.fpo_id = $1 OR t.farmer_id IS NULL)
            ORDER BY t.created_at""", fpo)
        deals = await conn.fetch("""
            SELECT d.id::text, c.code AS cluster_code, d.status, d.qty_qtl, d.gross_value
            FROM deals d JOIN clusters c ON c.id = d.cluster_id
            JOIN collection_points cp ON cp.id = c.collection_point_id
            WHERE cp.fpo_id = $1 AND d.status IN ('CONFIRMED','PAYMENT_REPORTED','PAID') ORDER BY d.created_at""", fpo)
    return {"verify": verify,
            "tickets": [{"id": t["id"], "village": t["village"], "first_name": t["first_name"], "reason": t["reason"],
                         "status": t["status"], "created_at": t["created_at"].isoformat()} for t in tickets],
            "deals": [{"id": d["id"], "cluster_code": d["cluster_code"], "status": d["status"],
                       "qty_qtl": float(d["qty_qtl"]), "gross_value": float(d["gross_value"])} for d in deals]}


@router.post("/agent/clusters/{cid}/verification")
async def verification(cid: str, photo: UploadFile = File(...), grade: str = Form(...), lat: float = Form(...),
                       lon: float = Form(...), accuracy_m: float = Form(...), captured_at: str = Form(...),
                       moisture_pct: float | None = Form(default=None), who: dict = Depends(require("agent"))):
    if grade not in ("A", "B", "C", "REJECT"):
        raise ApiError(422, "BAD_GRADE")
    if accuracy_m > 200:
        raise ApiError(422, "LOW_ACCURACY")
    try:
        cap = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        if cap.tzinfo is None:
            cap = cap.replace(tzinfo=timezone.utc)
    except ValueError:
        raise ApiError(422, "BAD_CAPTURED_AT")
    now = datetime.now(timezone.utc)
    if now - cap > timedelta(minutes=10) or cap - now > timedelta(minutes=2):
        raise ApiError(422, "STALE_CAPTURE")
    if not (photo.content_type or "").startswith("image/"):
        raise ApiError(422, "BAD_PHOTO")
    data = await photo.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise ApiError(413, "PHOTO_TOO_LARGE")
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise ApiError(422, "BAD_PHOTO")                       # not a JPEG, PNG or WebP (a web page or script must never be stored)
    fpo = await _fpo(who["sub"])
    seqs: list[int] = []
    try:
        async with db.pool.acquire() as conn, conn.transaction():
            c = await conn.fetchrow("""SELECT c.id, c.status, cp.fpo_id,
                    ST_Distance(cp.geog, ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography) AS dist
                    FROM clusters c JOIN collection_points cp ON cp.id = c.collection_point_id
                    WHERE c.id = $1::uuid FOR UPDATE OF c""", cid, lon, lat)
            if not c:
                raise ApiError(404, "NOT_FOUND")
            if c["fpo_id"] != fpo:
                raise ApiError(403, "FORBIDDEN")
            if c["status"] != "READY":
                raise ApiError(409, "ALREADY_VERIFIED" if c["status"] != "OPEN" else "NOT_READY")
            if c["dist"] > settings.verify_radius_m:
                raise ApiError(422, "TOO_FAR", distance_m=round(c["dist"]), radius_m=settings.verify_radius_m)
            name = f"{uuid.uuid4().hex}.jpg"
            if grade == "REJECT":
                status = "OPEN"                           # sample failed: cluster keeps collecting
            else:
                status = "BIDDING"
                settings.media_dir.joinpath("v").mkdir(parents=True, exist_ok=True)
                (settings.media_dir / "v" / name).write_bytes(data)
                await conn.execute("""INSERT INTO verifications (cluster_id, agent_id, grade, moisture_pct, photo_path,
                        geog, accuracy_m, distance_m, captured_at)
                        VALUES ($1, $2::uuid, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326)::geography, $8, $9, $10)""",
                                   c["id"], who["sub"], grade, moisture_pct, name, lon, lat, accuracy_m, c["dist"], cap)
            ends = await conn.fetchval("""UPDATE clusters SET status = $2, grade = $3, version = version + 1,
                    bidding_ends_at = CASE WHEN $2 = 'BIDDING' THEN now() + $4 ELSE NULL END, updated_at = now()
                    WHERE id = $1 RETURNING bidding_ends_at""", c["id"], status,
                                       None if grade == "REJECT" else grade, timedelta(seconds=settings.auction_s))
            seqs.append(await events.emit(conn, "cluster.updated", await views.cluster_view(conn, c["id"])))
    except asyncpg.DataError:
        raise ApiError(404, "NOT_FOUND")
    await events.publish(seqs)
    return JSONResponse({"cluster_id": cid, "status": status, "bidding_ends_at": ends.isoformat() if ends else None},
                        status_code=201)


@router.post("/agent/triage/{tid}/claim")
async def claim(tid: str, who: dict = Depends(require("agent"))):
    fpo = await _fpo(who["sub"])
    try:
        r = await db.pool.fetchrow("""UPDATE triage_tickets t SET status = 'ASSIGNED', agent_id = $2::uuid
            WHERE t.id = $1::uuid AND (t.status = 'OPEN' OR t.agent_id = $2::uuid)
              AND (t.farmer_id IS NULL OR EXISTS (SELECT 1 FROM farmers f WHERE f.id = t.farmer_id AND f.fpo_id = $3))
            RETURNING status""", tid, who["sub"], fpo)
        if not r:
            exists = await db.pool.fetchval("SELECT 1 FROM triage_tickets WHERE id = $1::uuid", tid)
            raise ApiError(409 if exists else 404, "ALREADY_CLAIMED" if exists else "NOT_FOUND")
    except asyncpg.DataError:
        raise ApiError(404, "NOT_FOUND")
    return {"status": "ASSIGNED"}


@router.post("/agent/triage/{tid}/bridge")
async def bridge(tid: str, who: dict = Depends(require("agent"))):
    """Simulated masked call: reveals the 2-digit code once, resolves the ticket, resets the farmer's failure count."""
    try:
        r = await db.pool.fetchrow("""UPDATE triage_tickets SET code_used = true, status = 'RESOLVED'
            WHERE id = $1::uuid AND agent_id = $2::uuid AND status = 'ASSIGNED' AND NOT code_used
              AND (code_expires_at IS NULL OR code_expires_at > now())
            RETURNING verbal_code, phone""", tid, who["sub"])
        if not r:
            row = await db.pool.fetchrow("SELECT agent_id::text, status, code_used FROM triage_tickets "
                                         "WHERE id = $1::uuid", tid)
            if not row:
                raise ApiError(404, "NOT_FOUND")
            if row["code_used"]:
                raise ApiError(409, "CODE_USED")
            raise ApiError(409, "NOT_CLAIMED")
    except asyncpg.DataError:
        raise ApiError(404, "NOT_FOUND")
    await cache.redis.delete(f"fail:{r['phone']}")
    return {"verbal_code": r["verbal_code"], "mode": "simulated"}


@router.post("/agent/deals/{did}/payment-confirmed")
async def payment_confirmed(did: str, who: dict = Depends(require("agent"))):
    fpo = await _fpo(who["sub"])
    try:
        async with db.pool.acquire() as conn, conn.transaction():
            d = await conn.fetchrow("""UPDATE deals d SET status = 'PAID', updated_at = now()
                FROM clusters c, collection_points cp
                WHERE d.id = $1::uuid AND c.id = d.cluster_id AND cp.id = c.collection_point_id AND cp.fpo_id = $2
                  AND d.status = 'PAYMENT_REPORTED' RETURNING d.buyer_id::text""", did, fpo)
            if not d:
                cur = await conn.fetchval("SELECT status FROM deals WHERE id = $1::uuid", did)
                if cur == "PAID":
                    return {"status": "PAID"}
                raise ApiError(404 if cur is None else 409, "NOT_FOUND" if cur is None else "PAYMENT_NOT_REPORTED")
            s1 = await events.emit(conn, "deal.updated", {"deal_id": did, "status": "PAID", "for_buyer": d["buyer_id"]},
                                   "buyer")
            s2 = await events.emit(conn, "deal.updated", {"deal_id": did, "status": "PAID"}, "agent")
    except asyncpg.DataError:
        raise ApiError(404, "NOT_FOUND")
    await events.publish([s1, s2])
    return {"status": "PAID"}
