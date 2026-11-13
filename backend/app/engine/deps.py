"""Postgres/Valkey implementation of the engine's dependencies. Owner: Darshan."""
import json
import logging
import random
import time

from .. import cache
from ..config import settings
from ..services import clustering

log = logging.getLogger("deps")
CONSENT_VERSION = "v1"

try:  # P4's module; absent until A3 merges
    from ..services import pricing as _pricing  # type: ignore
except Exception:
    _pricing = None


class PgDeps:
    provider = settings.provider
    call_cap_s = settings.call_cap_s

    def __init__(self, pool):
        self.pool = pool

    def now(self) -> float:
        return time.time()

    async def get_farmer(self, phone: str) -> dict | None:
        r = await self.pool.fetchrow("""SELECT id, lang, district_code, (consent_at IS NOT NULL) AS consented
                                        FROM farmers WHERE phone = $1 AND status = 'ACTIVE'""", phone)
        return dict(r) | {"id": str(r["id"])} if r else None

    async def set_lang(self, farmer_id, lang: str) -> None:
        await self.pool.execute("UPDATE farmers SET lang = $2 WHERE id = $1::uuid", farmer_id, lang)

    async def record_consent(self, farmer_id, session_id, lang: str, digit: str) -> None:
        async with self.pool.acquire() as c, c.transaction():
            await c.execute("""INSERT INTO consent_log (farmer_id, version, lang, session_id, digit)
                               VALUES ($1::uuid, $2, $3, $4::uuid, $5)""",
                            farmer_id, CONSENT_VERSION, lang, session_id, digit)
            if digit == "1":
                await c.execute("UPDATE farmers SET consent_version = $2, consent_at = now() WHERE id = $1::uuid",
                                farmer_id, CONSENT_VERSION)

    async def crop_menu(self, district: str, month: int) -> list[str]:
        rows = await self.pool.fetch("""SELECT crop_code FROM crop_calendar
                                        WHERE district_code = $1 AND month = $2 ORDER BY rank LIMIT 3""",
                                     district, month)
        if rows:
            return [r["crop_code"] for r in rows]
        # no calendar row for this month: fall back to any crops so a call never dead-ends
        return [r["code"] for r in await self.pool.fetch("SELECT code FROM crops ORDER BY code LIMIT 3")]

    async def get_crop(self, code: str) -> dict:
        r = await self.pool.fetchrow(
            "SELECT code, max_listing_qtl, min_price, max_price FROM crops WHERE code = $1", code)
        return {"code": r["code"], "max_listing_qtl": float(r["max_listing_qtl"]),
                "min_price": float(r["min_price"]), "max_price": float(r["max_price"])}

    async def has_live_listing(self, farmer_id, crop: str) -> bool:
        return bool(await self.pool.fetchval("""SELECT 1 FROM listings WHERE farmer_id = $1::uuid AND crop_code = $2
                       AND status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED')""", farmer_id, crop))

    async def has_any_live_listing(self, farmer_id) -> bool:
        return bool(await self.pool.fetchval("""SELECT 1 FROM listings WHERE farmer_id = $1::uuid
                       AND status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED') LIMIT 1""", farmer_id))

    async def get_floor(self, district: str, crop: str) -> dict | None:
        """P4's services/pricing.get_floor when merged; until then read the cached floor:* key. Never raises."""
        try:
            if _pricing:
                return await _pricing.get_floor(self.pool, cache.redis, district, crop)
            raw = await cache.redis.get(f"floor:{district}:{crop}")
            return json.loads(raw) if raw else None
        except Exception:
            log.exception("get_floor failed")
            return None

    async def commit_listing(self, s: dict) -> int:
        return await clustering.commit_listing(self.pool, s)

    async def open_ticket(self, phone: str, farmer_id, reason: str) -> str:
        """Open (or reuse) the helper ticket; returns the 2-digit code the IVR speaks. D3 adds expiry/use rules."""
        code = f"{random.randint(10, 99)}"
        await self.pool.execute("""
            INSERT INTO triage_tickets (phone, farmer_id, reason, verbal_code, code_expires_at)
            VALUES ($1, $2::uuid, $3, $4, now() + interval '24 hours') ON CONFLICT DO NOTHING""",
                                phone, farmer_id, reason, code)
        return await self.pool.fetchval("""SELECT verbal_code FROM triage_tickets
                       WHERE phone = $1 AND status IN ('OPEN','ASSIGNED')""", phone)

    async def record_failure(self, phone: str) -> int:
        """Count a failed call (24 h window) and return the running total."""
        k = f"fail:{phone}"
        n = await cache.redis.incr(k)
        if n == 1:
            await cache.redis.expire(k, 86400)
        return int(n)
