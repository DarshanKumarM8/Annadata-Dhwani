"""Glue used by every adapter. Owner: Darshan.

process(): idempotency check -> load session (Valkey, else Postgres checkpoint) -> engine -> CAS save ->
checkpoint -> evidence row in dtmf_events. Every accepted transition is therefore durable before the
adapter plays the next prompt.
"""
import logging

from .. import db
from . import flows, guard
from . import session as store
from .actions import Action, Event
from .engine import handle_event

log = logging.getLogger("engine.service")


def replay(s: dict | None) -> Action:
    """Answer for a duplicate event: repeat the current prompt, change nothing."""
    if s is None or s["state"] in flows.TERMINAL:
        return Action(hangup_now=True)
    return flows.build(s["state"], s)


async def log_dtmf(session_id: str, event_id: str, state_before: str, digits: str, state_after: str,
                   dropped: str | None = None) -> None:
    """Evidence trail row; UNIQUE(session_id, event_id) makes a retry harmless."""
    try:
        await db.pool.execute("""INSERT INTO dtmf_events (session_id, event_id, state_before, digits, state_after,
                                 dropped_reason) VALUES ($1::uuid, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING""",
                              session_id, event_id, state_before, digits, state_after, dropped)
    except Exception:
        log.exception("dtmf_events write failed")        # evidence must never break a live call


async def log_dropped(phone: str, event_id: str, state: str, digit: str, reason: str) -> None:
    """A press the adapter discarded (bounce) still gets an evidence row."""
    s = await store.load(phone)
    if s:
        await log_dtmf(s["id"], event_id, state, digit, state, reason)


async def process(deps, phone: str, ev: Event) -> Action:
    ev.phone = phone
    if ev.event_id and await guard.is_duplicate_event(ev.call_id, ev.event_id):
        return replay(await store.load(phone))
    s = await store.load(phone)
    expected = s["version"] if s else 0
    before = s["state"] if s else ""
    action, s2 = await handle_event(deps, s, ev)
    if s2 is not None:
        await store.save(s2, expected)
        await store.checkpoint(s2)
        if ev.kind in ("digits", "timeout"):
            await log_dtmf(s2["id"], ev.event_id or f"{ev.call_id}:{s2['version']}", before,
                           ev.digits, action.state or s2["state"])
    return action


async def mark_dropped(phone: str) -> None:
    """Caller hung up or the socket died mid-call: keep the session, record the outcome."""
    s = await store.load(phone)
    if s and s["state"] not in flows.TERMINAL:
        await store.mark_dropped(s["id"])
