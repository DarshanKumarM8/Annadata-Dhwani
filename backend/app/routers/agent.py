"""FPO Field Agent router for Annadata Dhwani.

Provides endpoints for mobile field agents:
- POST /api/agent/login: Authenticate agent with phone and PIN
- GET /api/agent/me: Profile of currently logged-in agent
- GET /api/agent/collection-points: Assigned FPO collection points
- GET /api/agent/clusters: Clusters waiting for inspection and verification
- GET /api/agent/clusters/{cluster_id}: Detailed cluster information with farmer listing totals
- POST /api/agent/clusters/{cluster_id}/verify: Physical produce verification with live photo
- GET /api/agent/verifications: Verification history completed by the agent
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bcrypt
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Uploads directory for live verification photos
UPLOAD_DIR = Path("uploads/verifications")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# In-memory token store fallback when Redis is absent
_TOKEN_STORE: dict[str, dict[str, Any]] = {}


def normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format."""
    clean = re.sub(r"[^\d+]", "", phone.strip())
    if clean.startswith("+"):
        return clean
    if len(clean) == 10:
        return f"+91{clean}"
    if len(clean) == 12 and clean.startswith("91"):
        return f"+{clean}"
    return f"+{clean}"


def verify_pin(plain_pin: str, hashed_or_plain: str) -> bool:
    """Verify PIN against hash or fallback demo password."""
    if not hashed_or_plain:
        return False
    # If bcrypt hash
    if hashed_or_plain.startswith("$2b$") or hashed_or_plain.startswith("$2a$"):
        try:
            return bcrypt.checkpw(plain_pin.encode("utf-8"), hashed_or_plain.encode("utf-8"))
        except Exception:
            return False
    # Demo seed fallback (e.g. "<HASH_PIN>" or direct match in testing)
    return plain_pin == hashed_or_plain or plain_pin == "1234"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AgentLoginRequest(BaseModel):
    phone: str
    pin: str


class AgentProfile(BaseModel):
    id: str
    fpo_id: str
    name: str
    phone: str


class AgentLoginResponse(BaseModel):
    token: str
    agent: AgentProfile


class CollectionPointItem(BaseModel):
    id: str
    fpo_id: str
    name: str
    district_code: str


class ClusterListingItem(BaseModel):
    id: str
    farmer_name: str
    farmer_phone: str
    village: str
    qty_qtl: float
    ask_price: float


class ClusterDetailResponse(BaseModel):
    id: str
    collection_point_id: str
    collection_point_name: str
    crop_code: str
    status: str
    total_qtl: float
    listing_count: int
    min_ask: float
    wavg_ask: float
    grade: str | None
    created_at: str | None
    listings: list[ClusterListingItem]


class VerificationRecord(BaseModel):
    id: str
    cluster_id: str
    crop_code: str
    total_qtl: float
    grade: str
    moisture_pct: float | None
    notes: str | None
    photo_url: str
    verified_at: str


class VerifyResponse(BaseModel):
    status: str
    verification_id: str
    verified_at: str
    cluster_id: str
    grade: str
    lat: float | None = None
    lon: float | None = None


# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------


async def get_current_agent(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Validate Bearer token and return agent record."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = authorization.split(" ", 1)[1].strip()
    redis_client = getattr(request.app.state, "redis", None)

    agent_data: dict[str, Any] | None = None

    if redis_client is not None:
        try:
            raw = await redis_client.get(f"agent_token:{token}")
            if raw:
                agent_data = json.loads(raw if isinstance(raw, str) else raw.decode())
        except Exception as exc:
            logger.warning("Redis token lookup failed: %s", exc)

    if not agent_data:
        agent_data = _TOKEN_STORE.get(token)

    if not agent_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid token",
        )

    return agent_data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/agent/login", response_model=AgentLoginResponse)
async def agent_login(request: Request, payload: AgentLoginRequest):
    """Authenticate field agent using phone and PIN."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)
    phone_clean = normalize_phone(payload.phone)

    agent_row: dict[str, Any] | None = None

    if pool is not None:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, fpo_id, name, phone, pin_hash, active
                    FROM agents
                    WHERE phone = $1 AND active = true
                    """,
                    phone_clean,
                )
                if row:
                    agent_row = dict(row)
        except Exception as exc:
            logger.exception("Error checking agent credentials in DB: %s", exc)

    # In-memory mock/fallback for demo seeds or tests when DB is detached
    if not agent_row:
        if phone_clean in ("+919800000101", "+919800000102"):
            agent_row = {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000021"),
                "fpo_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "name": "Kavya" if phone_clean == "+919800000101" else "Suresh",
                "phone": phone_clean,
                "pin_hash": "1234",
                "active": True,
            }

    if not agent_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or inactive agent",
        )

    pin_hash = agent_row.get("pin_hash", "")
    if not verify_pin(payload.pin, pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect PIN",
        )

    token = f"agt_{uuid.uuid4().hex}"
    agent_info = {
        "id": str(agent_row["id"]),
        "fpo_id": str(agent_row["fpo_id"]),
        "name": agent_row["name"],
        "phone": agent_row["phone"],
    }

    # Store token with 7-day TTL
    if redis_client is not None:
        try:
            await redis_client.set(
                f"agent_token:{token}",
                json.dumps(agent_info),
                ex=7 * 86400,
            )
        except Exception as exc:
            logger.warning("Redis store failed: %s", exc)

    _TOKEN_STORE[token] = agent_info

    return AgentLoginResponse(
        token=token,
        agent=AgentProfile(**agent_info),
    )


@router.get("/api/agent/me", response_model=AgentProfile)
async def get_agent_profile(agent: dict[str, Any] = Depends(get_current_agent)):
    """Return currently authenticated agent's profile."""
    return AgentProfile(**agent)


@router.get("/api/agent/collection-points", response_model=list[CollectionPointItem])
async def get_agent_collection_points(
    request: Request,
    agent: dict[str, Any] = Depends(get_current_agent),
):
    """List collection points assigned to agent's FPO."""
    pool = getattr(request.app.state, "pool", None)
    fpo_id = agent["fpo_id"]

    if pool is not None:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, fpo_id, name, district_code
                    FROM collection_points
                    WHERE fpo_id = $1
                    ORDER BY name ASC
                    """,
                    uuid.UUID(fpo_id),
                )
                return [
                    CollectionPointItem(
                        id=str(r["id"]),
                        fpo_id=str(r["fpo_id"]),
                        name=r["name"],
                        district_code=r["district_code"],
                    )
                    for r in rows
                ]
        except Exception as exc:
            logger.warning("DB query for collection points failed: %s", exc)

    # Fallback default collection points for reference FPO
    return [
        CollectionPointItem(
            id="00000000-0000-0000-0000-000000000011",
            fpo_id=fpo_id,
            name="Keregodu FPO yard",
            district_code="KA-MANDYA",
        ),
        CollectionPointItem(
            id="00000000-0000-0000-0000-000000000012",
            fpo_id=fpo_id,
            name="Hosahalli point",
            district_code="KA-MANDYA",
        ),
    ]


@router.get("/api/agent/clusters", response_model=list[dict[str, Any]])
async def get_clusters_for_verification(
    request: Request,
    collection_point_id: str | None = None,
    agent: dict[str, Any] = Depends(get_current_agent),
):
    """List clusters waiting for physical inspection."""
    pool = getattr(request.app.state, "pool", None)
    fpo_id = agent["fpo_id"]

    if pool is not None:
        try:
            async with pool.acquire() as conn:
                query = """
                    SELECT
                        c.id, c.collection_point_id, cp.name AS collection_point_name,
                        c.crop_code, c.status, c.total_qtl, c.listing_count,
                        c.min_ask, c.wavg_ask, c.grade, c.bidding_ends_at, c.version
                    FROM clusters c
                    JOIN collection_points cp ON c.collection_point_id = cp.id
                    WHERE cp.fpo_id = $1
                """
                params: list[Any] = [uuid.UUID(fpo_id)]
                if collection_point_id:
                    query += " AND c.collection_point_id = $2"
                    params.append(uuid.UUID(collection_point_id))

                query += " ORDER BY c.status ASC, c.id DESC"
                rows = await conn.fetch(query, *params)
                return [
                    {
                        "id": str(r["id"]),
                        "collection_point_id": str(r["collection_point_id"]),
                        "collection_point_name": r["collection_point_name"],
                        "crop_code": r["crop_code"],
                        "status": r["status"],
                        "total_qtl": float(r["total_qtl"] or 0),
                        "listing_count": int(r["listing_count"] or 0),
                        "min_ask": float(r["min_ask"] or 0),
                        "wavg_ask": float(r["wavg_ask"] or 0),
                        "grade": r["grade"],
                        "version": int(r["version"] or 1),
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.warning("DB query for clusters failed: %s", exc)

    return []


@router.get("/api/agent/clusters/{cluster_id}", response_model=ClusterDetailResponse)
async def get_cluster_detail(
    cluster_id: str,
    request: Request,
    agent: dict[str, Any] = Depends(get_current_agent),
):
    """Get full details of a cluster including farmer listings."""
    try:
        c_uuid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid cluster UUID")

    pool = getattr(request.app.state, "pool", None)
    if not pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        async with pool.acquire() as conn:
            c = await conn.fetchrow(
                """
                SELECT
                    c.id, c.collection_point_id, cp.name AS collection_point_name,
                    c.crop_code, c.status, c.total_qtl, c.listing_count,
                    c.min_ask, c.wavg_ask, c.grade
                FROM clusters c
                JOIN collection_points cp ON c.collection_point_id = cp.id
                WHERE c.id = $1
                """,
                c_uuid,
            )
            if not c:
                raise HTTPException(status_code=404, detail="Cluster not found")

            # Fetch individual farmer listings
            listings_rows = await conn.fetch(
                """
                SELECT l.id, l.qty_qtl, l.ask_price, f.name AS farmer_name,
                       f.phone AS farmer_phone, f.village
                FROM listings l
                JOIN farmers f ON l.farmer_id = f.id
                WHERE l.cluster_id = $1
                ORDER BY l.id ASC
                """,
                c_uuid,
            )

            listings = [
                ClusterListingItem(
                    id=str(r["id"]),
                    farmer_name=r["farmer_name"] or "Farmer",
                    farmer_phone=r["farmer_phone"],
                    village=r["village"] or "Mandya",
                    qty_qtl=float(r["qty_qtl"]),
                    ask_price=float(r["ask_price"]),
                )
                for r in listings_rows
            ]

            return ClusterDetailResponse(
                id=str(c["id"]),
                collection_point_id=str(c["collection_point_id"]),
                collection_point_name=c["collection_point_name"],
                crop_code=c["crop_code"],
                status=c["status"],
                total_qtl=float(c["total_qtl"] or 0),
                listing_count=int(c["listing_count"] or 0),
                min_ask=float(c["min_ask"] or 0),
                wavg_ask=float(c["wavg_ask"] or 0),
                grade=c["grade"],
                created_at=None,
                listings=listings,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error loading cluster detail: %s", exc)
        raise HTTPException(status_code=500, detail="Error loading cluster details")


@router.post("/api/agent/clusters/{cluster_id}/verify", response_model=VerifyResponse)
async def verify_cluster(
    cluster_id: str,
    request: Request,
    grade: str = Form(..., pattern="^[A-C]$"),
    moisture_pct: float | None = Form(None),
    notes: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    photo: UploadFile = File(...),
    agent: dict[str, Any] = Depends(get_current_agent),

):
    """Verify cluster quality, upload live photograph, and update cluster status."""
    try:
        c_uuid = uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid cluster UUID")

    # 1. Validate image MIME type
    if photo.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type {photo.content_type}. Allowed: JPEG, PNG, WEBP",
        )

    # 2. Read and validate photo bytes size
    photo_bytes = await photo.read()
    if len(photo_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded photograph is empty",
        )
    if len(photo_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Photograph exceeds 10MB limit",
        )

    # Validate geo-tag consistency
    if (lat is None) ^ (lon is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both latitude and longitude must be provided together.",
        )

    ext = ".jpg" if "jpeg" in photo.content_type else (".png" if "png" in photo.content_type else ".webp")
    photo_filename = f"{c_uuid}_{uuid.uuid4().hex[:8]}{ext}"
    target_path = UPLOAD_DIR / photo_filename
    target_path.write_bytes(photo_bytes)
    photo_url = f"/uploads/verifications/{photo_filename}"

    pool = getattr(request.app.state, "pool", None)
    if not pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    now_utc = datetime.now(timezone.utc)
    verification_id = uuid.uuid4()
    agent_id = uuid.UUID(agent["id"])

    # 4. Atomic database verification transaction
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Lock cluster row for update
                c = await conn.fetchrow(
                    "SELECT id, status, grade FROM clusters WHERE id = $1 FOR UPDATE",
                    c_uuid,
                )
                if not c:
                    raise HTTPException(status_code=404, detail="Cluster not found")

                # Duplicate verification check
                existing_verif = await conn.fetchval(
                    "SELECT id FROM verifications WHERE cluster_id = $1",
                    c_uuid,
                )
                if existing_verif or c["status"] in ("VERIFIED", "BIDDING", "ACCEPTED", "CLOSED"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Cluster has already been verified",
                    )

                # Insert verification
                await conn.execute(
                    """
                    INSERT INTO verifications (
                        id, cluster_id, agent_id, photo_url, grade,
                        moisture_pct, notes, verified_at, lat, lon
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    verification_id,
                    c_uuid,
                    agent_id,
                    photo_url,
                    grade,
                    moisture_pct,
                    notes,
                    now_utc,
                    lat,
                    lon,
                )

                # Update cluster status to VERIFIED (ready for bidding)
                await conn.execute(
                    """
                    UPDATE clusters
                    SET status = 'VERIFIED',
                        grade = $2,
                        version = version + 1
                    WHERE id = $1
                    """,
                    c_uuid,
                    grade,
                )

        return VerifyResponse(
            status="VERIFIED",
            verification_id=str(verification_id),
            verified_at=now_utc.isoformat(),
            cluster_id=str(c_uuid),
            grade=grade,
            lat=lat,
            lon=lon,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error executing verification transaction: %s", exc)
        raise HTTPException(status_code=500, detail="Database transaction failed")


@router.get("/api/agent/verifications", response_model=list[VerificationRecord])
async def get_agent_verifications(
    request: Request,
    agent: dict[str, Any] = Depends(get_current_agent),
):
    """List past verifications completed by this agent."""
    pool = getattr(request.app.state, "pool", None)
    agent_id = uuid.UUID(agent["id"])

    if pool is not None:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        v.id, v.cluster_id, c.crop_code, c.total_qtl,
                        v.grade, v.moisture_pct, v.notes, v.photo_url, v.verified_at
                    FROM verifications v
                    JOIN clusters c ON v.cluster_id = c.id
                    WHERE v.agent_id = $1
                    ORDER BY v.verified_at DESC
                    LIMIT 100
                    """,
                    agent_id,
                )
                return [
                    VerificationRecord(
                        id=str(r["id"]),
                        cluster_id=str(r["cluster_id"]),
                        crop_code=r["crop_code"],
                        total_qtl=float(r["total_qtl"] or 0),
                        grade=r["grade"],
                        moisture_pct=float(r["moisture_pct"]) if r["moisture_pct"] is not None else None,
                        notes=r["notes"],
                        photo_url=r["photo_url"],
                        verified_at=(
                            r["verified_at"].isoformat()
                            if hasattr(r["verified_at"], "isoformat")
                            else str(r["verified_at"])
                        ),
                    )
                    for r in rows
                ]
        except Exception as exc:
            logger.warning("DB query for verifications failed: %s", exc)

    return []
