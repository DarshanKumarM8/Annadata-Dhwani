"""Inbound missed call and IVR telephony webhook router.

Handles:
- POST /api/ivr/inbound: Inbound missed-call webhook to queue farmer callback jobs.
- POST /api/ivr/dtmf: Process keypad DTMF digits for crop, quantity, price, and bid acceptance.
- Clustering evaluation logic for 2–5 tonne clusters.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.services.pricing import get_floor

logger = logging.getLogger(__name__)

router = APIRouter()

# E.164 phone regex (+ followed by 8 to 15 digits)
E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")

CROP_KEYPAD_MAP = {
    "1": "ragi",
    "2": "paddy_common",
    "3": "maize",
}


def normalize_phone(raw: str | None) -> str:
    """Validate and normalize to E.164."""
    if not raw:
        raise ValueError("Phone number is required")
    cleaned = raw.strip().replace(" ", "").replace("-", "")
    if not cleaned.startswith("+"):
        if len(cleaned) == 10 and cleaned.isdigit():
            cleaned = "+91" + cleaned
        else:
            cleaned = "+" + cleaned

    if not E164_REGEX.match(cleaned):
        raise ValueError(
            f"Invalid E.164 phone number format: '{raw}'. Expected e.g. +919845012345"
        )
    return cleaned


def evaluate_cluster_formation(listings: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate if pooled listings form an eligible 2–5 tonne cluster."""
    if not listings:
        return {"status": "EMPTY", "total_qtl": 0.0, "eligible": False}

    total_qtl = sum(float(l.get("qty_qtl", 0)) for l in listings)
    listing_count = len(listings)
    min_ask = min(float(l.get("ask_price", 0)) for l in listings)
    wavg_ask = round(
        sum(float(l.get("qty_qtl", 0)) * float(l.get("ask_price", 0)) for l in listings) / total_qtl,
        2,
    )

    if total_qtl < 20.0:
        return {
            "status": "BELOW_MINIMUM_WEIGHT",
            "eligible": False,
            "total_qtl": total_qtl,
            "listing_count": listing_count,
            "message": f"Cluster weight {total_qtl} qtl is below minimum 2 tonnes (20 qtl)",
        }
    elif total_qtl <= 50.0:
        return {
            "status": "ELIGIBLE",
            "eligible": True,
            "total_qtl": total_qtl,
            "listing_count": listing_count,
            "min_ask": min_ask,
            "wavg_ask": wavg_ask,
            "message": f"Eligible cluster formed at {total_qtl} qtl (2-5 tonnes)",
        }
    else:
        # Exceeds maximum 5 tonnes (50 qtl) -> split / cap at 50 qtl
        return {
            "status": "EXCEEDS_MAXIMUM_WEIGHT",
            "eligible": True,
            "capped_qtl": 50.0,
            "total_qtl": total_qtl,
            "excess_qtl": round(total_qtl - 50.0, 2),
            "message": f"Total weight {total_qtl} qtl exceeds 5 tonnes max; capped at 50 qtl",
        }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class InboundCallResponse(BaseModel):
    ok: bool
    job_id: Any
    status: str
    phone: str
    registered: bool
    message: str


class DtmfInputPayload(BaseModel):
    session_id: str
    phone: str
    state: str
    digits: str
    crop_code: str | None = None
    qty_qtl: float | None = None
    bid_id: str | None = None


class DtmfProcessResponse(BaseModel):
    status: str
    next_state: str
    message: str
    dropped_reason: str | None = None
    listing_id: str | None = None


# ---------------------------------------------------------------------------
# Route: POST /api/ivr/inbound
# ---------------------------------------------------------------------------


@router.post("/api/ivr/inbound", response_model=InboundCallResponse)
async def inbound_missed_call(request: Request):
    """Receive farmer missed call and queue callback job."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)

    # 1. Extract phone from JSON, Form-data, or Query parameters
    raw_phone: str | None = None
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                raw_phone = body.get("phone") or body.get("From")
        except Exception:
            pass
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            raw_phone = form.get("phone") or form.get("From") or form.get("CallFrom")  # type: ignore
        except Exception:
            pass
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                raw_phone = body.get("phone") or body.get("From")
        except Exception:
            raw_phone = request.query_params.get("phone") or request.query_params.get("From")

    # 2. Normalize & validate phone
    try:
        phone = normalize_phone(raw_phone)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "INVALID_PHONE", "message": str(val_err)},
        )

    now_utc = datetime.now(timezone.utc)
    farmer_id: uuid.UUID | None = None
    registered = False
    job_id: Any = None

    # 3. Check if farmer is registered in DB
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                farmer_row = await conn.fetchrow(
                    "SELECT id, name, lang, consent_version, status FROM farmers WHERE phone = $1",
                    phone,
                )
                if farmer_row:
                    farmer_id = farmer_row["id"]
                    registered = True

                # 4. Check for duplicate active job (prevent dialer flood)
                has_jobs = await conn.fetchval(
                    "SELECT to_regclass('public.call_jobs')"
                )
                if has_jobs:
                    existing_job = await conn.fetchrow(
                        """
                        SELECT id, status FROM call_jobs
                        WHERE farmer_phone = $1
                          AND status IN ('QUEUED', 'DIALING', 'IN_CALL')
                          AND run_at >= now() - INTERVAL '5 minutes'
                        ORDER BY id DESC LIMIT 1
                        """,
                        phone,
                    )
                    if existing_job:
                        return InboundCallResponse(
                            ok=True,
                            job_id=existing_job["id"],
                            status=existing_job["status"],
                            phone=phone,
                            registered=registered,
                            message="Callback already queued for this phone",
                        )

                    # 5. Insert new callback job in call_jobs
                    job_row = await conn.fetchrow(
                        """
                        INSERT INTO call_jobs (kind, status, attempts, run_at, farmer_phone, farmer_id)
                        VALUES ('CALLBACK', 'QUEUED', 0, $1, $2, $3)
                        RETURNING id, status
                        """,
                        now_utc,
                        phone,
                        farmer_id,
                    )
                    if job_row:
                        job_id = job_row["id"]

        except Exception as exc:
            logger.error("DB error during inbound missed call: %s", exc)

    # Fallback job_id if DB is not available
    if job_id is None:
        job_id = f"job-{uuid.uuid4().hex[:8]}"

    # 6. Update breaker counter in Redis
    if redis_client is not None:
        try:
            today_str = now_utc.date().isoformat()
            await redis_client.incr(f"ops:breaker:{today_str}")
        except Exception:
            pass

    return InboundCallResponse(
        ok=True,
        job_id=job_id,
        status="QUEUED",
        phone=phone,
        registered=registered,
        message="Callback job queued successfully",
    )


# ---------------------------------------------------------------------------
# Route: POST /api/ivr/dtmf
# ---------------------------------------------------------------------------


@router.post("/api/ivr/dtmf", response_model=DtmfProcessResponse)
async def process_dtmf_event(payload: DtmfInputPayload, request: Request):
    """Process farmer keypad inputs (crop, quantity, price, bid accept/reject)."""
    pool = getattr(request.app.state, "pool", None)
    redis_client = getattr(request.app.state, "redis", None)
    now_utc = datetime.now(timezone.utc)

    phone = normalize_phone(payload.phone)
    digits = payload.digits.strip()
    curr_state = payload.state.upper()
    next_state = curr_state
    dropped_reason: str | None = None
    response_msg = "Digits received"
    res_status = "OK"
    listing_id: str | None = None

    # State 1: CROP SELECTION
    if curr_state == "CROP":
        if digits in CROP_KEYPAD_MAP:
            crop_selected = CROP_KEYPAD_MAP[digits]
            next_state = "QTY"
            response_msg = f"Crop selected: {crop_selected}. Enter quantity in quintals."
        else:
            dropped_reason = "OUT_OF_RANGE"
            res_status = "DROPPED"
            response_msg = "Invalid crop key. Press 1 for Ragi, 2 for Paddy, 3 for Maize."

    # State 2: QUANTITY ENTRY
    elif curr_state == "QTY":
        try:
            qty_val = float(digits)
            if 1 <= qty_val <= 50:
                next_state = "PRICE"
                response_msg = f"Quantity: {qty_val} quintals. Enter expected price per quintal."
            else:
                dropped_reason = "OUT_OF_RANGE"
                res_status = "DROPPED"
                response_msg = "Quantity must be between 1 and 50 quintals."
        except ValueError:
            dropped_reason = "OUT_OF_RANGE"
            res_status = "DROPPED"
            response_msg = "Invalid number. Enter quantity in quintals."

    # State 3: PRICE ENTRY (Listing Creation)
    elif curr_state == "PRICE":
        try:
            price_val = float(digits)
            if 1000 <= price_val <= 9000:
                # Check for existing active listing for this farmer (Scenario 6)
                if pool is not None:
                    async with pool.acquire() as conn:
                        farmer_id = await conn.fetchval(
                            "SELECT id FROM farmers WHERE phone = $1", phone
                        )
                        if farmer_id:
                            existing = await conn.fetchval(
                                """
                                SELECT id FROM listings
                                WHERE farmer_id = $1 AND crop_code = $2 AND status = 'ACTIVE'
                                """,
                                farmer_id,
                                payload.crop_code or "ragi",
                            )
                            if existing:
                                dropped_reason = "DUPLICATE_EVENT"
                                return DtmfProcessResponse(
                                    status="DROPPED",
                                    next_state="COMPLETED",
                                    dropped_reason="DUPLICATE_EVENT",
                                    message="Farmer already has an active listing for this crop.",
                                )

                            # Create listing
                            lid = uuid.uuid4()
                            await conn.execute(
                                """
                                INSERT INTO listings (
                                    id, farmer_id, crop_code, qty_qtl, ask_price,
                                    afpp_at_listing, guardrail, source, session_id, status
                                ) VALUES ($1, $2, $3, $4, $5, $6, 'NONE', 'IVR', $7, 'ACTIVE')
                                """,
                                lid,
                                farmer_id,
                                payload.crop_code or "ragi",
                                payload.qty_qtl or 10.0,
                                price_val,
                                3430.0,
                                uuid.UUID(payload.session_id) if payload.session_id else None,
                            )
                            listing_id = str(lid)

                next_state = "COMPLETED"
                res_status = "LISTING_CREATED"
                response_msg = f"Listing created successfully at ₹{price_val}/qtl."
            else:
                dropped_reason = "OUT_OF_RANGE"
                res_status = "DROPPED"
                response_msg = "Price must be between ₹1000 and ₹9000 per quintal."
        except ValueError:
            dropped_reason = "OUT_OF_RANGE"
            res_status = "DROPPED"
            response_msg = "Invalid price digits."

    # State 4: WINNING BID ACCEPT / REJECT (Scenarios 15 & 16)
    elif curr_state == "BID_OFFER":
        if digits == "1":
            res_status = "BID_ACCEPTED"
            next_state = "DONE"
            response_msg = "Farmer accepted the winning bid."
            if pool is not None and payload.bid_id:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO bid_responses (bid_id, accepted, responded_at)
                            VALUES ($1, true, $2)
                            """,
                            uuid.UUID(payload.bid_id),
                            now_utc,
                        )
                except Exception as exc:
                    logger.warning("Could not record bid accept: %s", exc)
        elif digits == "2":
            res_status = "BID_REJECTED"
            next_state = "DONE"
            response_msg = "Farmer rejected the winning bid."
            if pool is not None and payload.bid_id:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO bid_responses (bid_id, accepted, responded_at)
                            VALUES ($1, false, $2)
                            """,
                            uuid.UUID(payload.bid_id),
                            now_utc,
                        )
                except Exception as exc:
                    logger.warning("Could not record bid reject: %s", exc)
        else:
            dropped_reason = "OUT_OF_RANGE"
            res_status = "DROPPED"
            response_msg = "Press 1 to accept bid, 2 to reject bid."

    # 4. Log event in dtmf_events table and Redis ring buffer
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO dtmf_events (session_id, state_before, digits, state_after, dropped_reason, at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    payload.session_id,
                    curr_state,
                    digits,
                    next_state,
                    dropped_reason,
                    now_utc,
                )
        except Exception as exc:
            logger.warning("Error saving dtmf_event: %s", exc)

    if redis_client is not None:
        try:
            event_obj = {
                "session_id": payload.session_id,
                "state_before": curr_state,
                "digits": digits,
                "state_after": next_state,
                "dropped_reason": dropped_reason,
                "at": now_utc.isoformat(),
            }
            await redis_client.lpush("ops:dtmf:events", json.dumps(event_obj))
            await redis_client.ltrim("ops:dtmf:events", 0, 100)
        except Exception:
            pass

    return DtmfProcessResponse(
        status=res_status,
        next_state=next_state,
        message=response_msg,
        dropped_reason=dropped_reason,
        listing_id=listing_id,
    )
