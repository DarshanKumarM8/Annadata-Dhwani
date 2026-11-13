"""Buyer-facing cluster endpoints (contract C4). Owner: Darshan. D5 adds bids, deals and the agent/admin routes."""
import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .. import db
from ..services import views
from .auth import require

router = APIRouter(prefix="/api")


@router.get("/clusters")
async def list_clusters(status: str | None = None, crop: str | None = None, who: dict = Depends(require("buyer"))):
    statuses = [x for x in status.split(",") if x] if status else None
    async with db.pool.acquire() as conn:
        return {"clusters": await views.cluster_list(conn, statuses, crop or None, who["sub"])}


@router.get("/clusters/{cid}")
async def get_cluster(cid: str, who: dict = Depends(require("buyer"))):
    try:
        async with db.pool.acquire() as conn:
            out = await views.cluster_detail(conn, cid, who["sub"])
    except (ValueError, asyncpg.DataError):             # malformed uuid
        out = None
    return out or JSONResponse({"error": "NOT_FOUND"}, status_code=404)
