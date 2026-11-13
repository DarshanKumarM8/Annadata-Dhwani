"""Session store: Valkey is the fast copy, Postgres call_sessions is the durable checkpoint. Owner: Darshan.

Every accepted transition is written to Valkey with compare-and-set (lua/session_cas.lua) and then upserted into
call_sessions. If Valkey has lost the session (FLUSHALL, restart, eviction) load() rebuilds it from the checkpoint
when it is under 30 minutes old, so a call continues exactly where it was.
"""
import json
import logging
import uuid

from .. import cache, db
from ..config import settings
from .flows import TERMINAL

log = logging.getLogger("session")
REHYDRATE_WINDOW = "30 minutes"
EXTRA = ("retries", "lang", "started_at", "district_code")   # session fields kept inside the jsonb `data` column


class SessionConflict(Exception):
    """Another handler wrote the session first (stale version)."""


def key(phone: str) -> str:
    return f"sess:{phone}"


async def load(phone: str) -> dict | None:
    raw = await cache.redis.get(key(phone))
    if raw:
        return json.loads(raw)
    row = await db.pool.fetchrow(f"""
        SELECT * FROM call_sessions WHERE phone = $1 AND ended_at IS NULL
        AND updated_at > now() - interval '{REHYDRATE_WINDOW}' ORDER BY updated_at DESC LIMIT 1""", phone)
    if not row:
        return None
    data = dict(row["data"])
    extra = data.pop("_s", {})
    log.info("rehydrated session for %s at state %s", phone, row["state"])
    return {"id": str(row["id"]), "phone": phone, "farmer_id": str(row["farmer_id"]) if row["farmer_id"] else None,
            "kind": row["kind"], "provider": row["provider"], "call_id": row["provider_call_id"],
            "state": row["state"], "data": data, "version": row["version"], **{k: extra.get(k) for k in EXTRA}}


async def save(s: dict, expected_version: int) -> None:
    """Write s with version expected_version+1; raises SessionConflict if someone else moved first."""
    s["version"] = expected_version + 1
    res = await cache.scripts["session_cas"](
        keys=[key(s["phone"])], args=[expected_version, json.dumps(s), settings.session_ttl_s])
    if res == 1:
        return
    if res == -1:
        # the key vanished (TTL, FLUSHALL) between load and save: write it fresh
        await cache.redis.set(key(s["phone"]), json.dumps(s), ex=settings.session_ttl_s)
        return
    raise SessionConflict(s["phone"])


def outcome_of(s: dict) -> str | None:
    if s["state"] not in TERMINAL:
        return None
    return "FAILED_INPUT" if s["data"].get("failed_input") else "COMPLETED"


async def checkpoint(s: dict) -> None:
    """Upsert the durable copy. A newer version always wins, so a late writer cannot roll the session back."""
    outcome = outcome_of(s)
    data = {**s["data"], "_s": {k: s.get(k) for k in EXTRA}}
    await db.pool.execute("""
        INSERT INTO call_sessions (id, phone, farmer_id, kind, provider, provider_call_id, state, data, version,
                                   outcome, ended_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CASE WHEN $10::text IS NULL THEN NULL ELSE now() END)
        ON CONFLICT (id) DO UPDATE SET provider_call_id = EXCLUDED.provider_call_id, state = EXCLUDED.state,
          data = EXCLUDED.data, version = EXCLUDED.version, outcome = EXCLUDED.outcome,
          ended_at = EXCLUDED.ended_at, updated_at = now()
        WHERE call_sessions.version <= EXCLUDED.version""",
        uuid.UUID(s["id"]), s["phone"], uuid.UUID(s["farmer_id"]) if s["farmer_id"] else None, s["kind"],
        s["provider"], s["call_id"], s["state"], data, s["version"], outcome)


async def mark_dropped(session_id: str) -> None:
    """The caller hung up before a terminal state. The session stays resumable for 30 minutes."""
    await db.pool.execute("UPDATE call_sessions SET outcome = 'DROPPED' WHERE id = $1 AND ended_at IS NULL",
                          uuid.UUID(session_id))


async def expire_stale() -> int:
    """Sweeper: sessions untouched for 30 minutes are abandoned (the draft is dropped)."""
    res = await db.pool.execute(f"""UPDATE call_sessions SET outcome = 'EXPIRED', ended_at = now()
        WHERE ended_at IS NULL AND updated_at < now() - interval '{REHYDRATE_WINDOW}'""")
    return int(res.split()[-1])
