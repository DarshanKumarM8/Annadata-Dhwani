"""Buyer login and token checks. Owner: Darshan. D5 adds the agent login and the remaining role rules.

JWT HS256, 12 h, bcrypt. Five wrong passwords lock the account for 15 minutes (429 LOCKED).
Admin is the buyer row whose email starts with 'admin@'.
"""
import asyncio
import time

import bcrypt
import jwt
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from .. import cache, db
from ..config import settings

router = APIRouter(prefix="/api/auth")
TTL_S = 12 * 3600
MAX_FAILS, LOCK_S = 5, 900


class ApiError(Exception):
    def __init__(self, status: int, code: str, **extra):
        self.status, self.body = status, {"error": code, **extra}


def make_token(sub: str, role: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": sub, "role": role, "iat": now, "exp": now + TTL_S}, settings.jwt_secret,
                      algorithm="HS256")


def decode(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def require(*roles: str):
    """FastAPI dependency: a valid token whose role is one of `roles` (admin also passes for 'buyer')."""
    async def dep(authorization: str | None = Header(default=None)) -> dict:
        claims = decode(authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
        if not claims:
            raise ApiError(401, "UNAUTHENTICATED")
        if claims["role"] not in roles and not (claims["role"] == "admin" and "buyer" in roles):
            raise ApiError(403, "FORBIDDEN")
        return claims
    return dep


@router.post("/buyer/login")
async def buyer_login(body: dict):
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not email or not password:
        return JSONResponse({"error": "BAD_CREDENTIALS"}, status_code=401)
    key = f"rl:login:{email}"
    if int(await cache.redis.get(key) or 0) >= MAX_FAILS:
        return JSONResponse({"error": "LOCKED"}, status_code=429)
    row = await db.pool.fetchrow("SELECT id, org_name, status, password_hash FROM buyers WHERE email = $1", email)
    ok = bool(row) and await asyncio.to_thread(bcrypt.checkpw, password.encode(), row["password_hash"].encode())
    if not ok:
        if await cache.redis.incr(key) == 1:
            await cache.redis.expire(key, LOCK_S)
        return JSONResponse({"error": "BAD_CREDENTIALS"}, status_code=401)
    if row["status"] != "APPROVED":
        return JSONResponse({"error": "NOT_APPROVED", "status": row["status"]}, status_code=403)
    await cache.redis.delete(key)
    role = "admin" if email.startswith("admin@") else "buyer"
    return {"token": make_token(str(row["id"]), role),
            "buyer": {"id": str(row["id"]), "org_name": row["org_name"], "status": row["status"]}}
