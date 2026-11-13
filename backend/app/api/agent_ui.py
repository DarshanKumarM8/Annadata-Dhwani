"""Endpoints the FPO agent screen (frontend/src/routes/AgentApp.tsx) calls. Owner: Darshan.

The screen was built against another response shape than contract C4. Rather than fork the logic, these are thin adapters over
the real login and verification code (api/agent.py), so the same rules apply: JWT login with lockout, 500 m geofence, photo and
capture checks, one verification per cluster, live events on the feed. Farmers appear by first name, village and a MASKED phone
(+91•••••1234); a full number never leaves the server.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import db
from ..config import settings
from . import agent as core
from .auth import ApiError, require

router = APIRouter(prefix="/api/agent")


def _mask(phone: str) -> str:
    return "+91•••••" + phone[-4:]


@router.post("/login")
async def login(body: dict):
    """Same as POST /api/auth/agent/login, with the agent's phone added to the profile (the screen shows it)."""
    out = await core.agent_login(body)
    if isinstance(out, JSONResponse):                      # BAD_CREDENTIALS / LOCKED
        return out
    row = await db.pool.fetchrow("SELECT phone FROM agents WHERE id = $1::uuid", out["agent"]["id"])
    out["agent"]["phone"] = row["phone"] if row else str(body.get("phone", ""))
    return out


@router.get("/me")
async def me(who: dict = Depends(require("agent"))):
    r = await db.pool.fetchrow("SELECT id::text, fpo_id::text, name, phone FROM agents WHERE id = $1::uuid", who["sub"])
    return dict(r)


@router.get("/collection-points")
async def collection_points(who: dict = Depends(require("agent"))):
    fpo = await core._fpo(who["sub"])
    rows = await db.pool.fetch("""SELECT id::text, fpo_id::text, name, district_code FROM collection_points
                                  WHERE fpo_id = $1 ORDER BY name""", fpo)
    return [dict(r) for r in rows]


_CLUSTER_COLS = """c.id::text AS id, c.collection_point_id::text AS collection_point_id, cp.name AS collection_point_name,
                   c.crop_code, c.status, c.total_qtl, c.listing_count, c.min_ask, c.wavg_ask, c.grade, c.version,
                   ST_Y(cp.geog::geometry) AS yard_lat, ST_X(cp.geog::geometry) AS yard_lon"""


def _cluster(r) -> dict:
    return {"id": r["id"], "collection_point_id": r["collection_point_id"],
            "collection_point_name": r["collection_point_name"], "crop_code": r["crop_code"], "status": r["status"],
            "total_qtl": float(r["total_qtl"] or 0), "listing_count": int(r["listing_count"] or 0),
            "min_ask": float(r["min_ask"] or 0), "wavg_ask": float(r["wavg_ask"] or 0), "grade": r["grade"],
            "version": int(r["version"] or 1), "yard_lat": r["yard_lat"], "yard_lon": r["yard_lon"],
            "verify_radius_m": settings.verify_radius_m}


@router.get("/clusters")
async def clusters(collection_point_id: str | None = None, who: dict = Depends(require("agent"))):
    fpo = await core._fpo(who["sub"])
    try:
        rows = await db.pool.fetch(f"""SELECT {_CLUSTER_COLS} FROM clusters c JOIN collection_points cp ON cp.id = c.collection_point_id
            WHERE cp.fpo_id = $1 AND ($2::uuid IS NULL OR c.collection_point_id = $2::uuid)
            ORDER BY CASE c.status WHEN 'READY' THEN 0 WHEN 'OPEN' THEN 1 WHEN 'BIDDING' THEN 2 ELSE 3 END, c.code DESC""",
                                   fpo, collection_point_id)
    except Exception:
        raise ApiError(404, "NOT_FOUND")
    return [_cluster(r) for r in rows]


@router.get("/clusters/{cid}")
async def cluster_detail(cid: str, who: dict = Depends(require("agent"))):
    fpo = await core._fpo(who["sub"])
    try:
        c = await db.pool.fetchrow(f"""SELECT {_CLUSTER_COLS}, c.opened_at FROM clusters c
            JOIN collection_points cp ON cp.id = c.collection_point_id WHERE c.id = $1::uuid AND cp.fpo_id = $2""", cid, fpo)
        if not c:
            raise ApiError(404, "NOT_FOUND")
        lots = await db.pool.fetch("""SELECT l.id::text, l.qty_qtl, l.ask_price, f.name, f.phone, f.village FROM listings l
            JOIN farmers f ON f.id = l.farmer_id WHERE l.cluster_id = $1::uuid
            AND l.status IN ('ACTIVE','ACCEPTED','SOLD') ORDER BY l.ask_price, l.created_at""", cid)
    except ApiError:
        raise
    except Exception:
        raise ApiError(404, "NOT_FOUND")
    return {**_cluster(c), "created_at": c["opened_at"].isoformat(),
            "listings": [{"id": x["id"], "farmer_name": (x["name"] or "Farmer").split(" ")[0], "farmer_phone": _mask(x["phone"]),
                          "village": x["village"] or "", "qty_qtl": float(x["qty_qtl"]), "ask_price": float(x["ask_price"])}
                         for x in lots]}


@router.post("/clusters/{cid}/verify")
async def verify(cid: str, photo: UploadFile = File(...), grade: str = Form(..., pattern="^(A|B|C|REJECT)$"),
                 moisture_pct: float | None = Form(None), notes: str | None = Form(None), lat: float | None = Form(None),
                 lon: float | None = Form(None), accuracy_m: float | None = Form(None), captured_at: str | None = Form(None),
                 who: dict = Depends(require("agent"))):
    """The screen sends no accuracy or capture time: the capture is taken to be now, accuracy 50 m. Location is mandatory."""
    if lat is None or lon is None:
        raise ApiError(422, "LOCATION_REQUIRED")                # no GPS fix: the 500 m check cannot pass
    now = datetime.now(timezone.utc).isoformat()
    res = await core.verification(cid, photo, grade, lat, lon, 50.0 if accuracy_m is None else accuracy_m,
                                  captured_at or now, moisture_pct, who)
    body = json.loads(res.body)
    v = await db.pool.fetchrow("SELECT id::text, created_at FROM verifications WHERE cluster_id = $1::uuid", cid)
    return JSONResponse({"status": body["status"], "verification_id": v["id"] if v else "", "cluster_id": body["cluster_id"],
                         "verified_at": v["created_at"].isoformat() if v else now, "grade": grade, "lat": lat, "lon": lon,
                         "bidding_ends_at": body.get("bidding_ends_at")}, status_code=201)


@router.get("/verifications")
async def verifications(who: dict = Depends(require("agent"))):
    rows = await db.pool.fetch("""SELECT v.id::text, v.cluster_id::text, c.crop_code, c.total_qtl, v.grade, v.moisture_pct,
            regexp_replace(v.photo_path, '^.*[/\\\\]', '') AS photo, v.created_at
        FROM verifications v JOIN clusters c ON c.id = v.cluster_id WHERE v.agent_id = $1::uuid
        ORDER BY v.created_at DESC LIMIT 50""", who["sub"])
    return [{"id": r["id"], "cluster_id": r["cluster_id"], "crop_code": r["crop_code"], "total_qtl": float(r["total_qtl"]),
             "grade": r["grade"], "moisture_pct": float(r["moisture_pct"]) if r["moisture_pct"] is not None else None,
             "notes": None, "photo_url": "/media/v/" + r["photo"], "verified_at": r["created_at"].isoformat()} for r in rows]
