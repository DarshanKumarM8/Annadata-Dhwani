"""Glue used by every adapter: load session, run the engine, save session. Owner: Darshan."""
import logging

from . import session as store
from .actions import Action, Event
from .engine import handle_event

log = logging.getLogger("engine.service")


async def process(deps, phone: str, ev: Event) -> Action:
    ev.phone = phone
    s = await store.load(phone)
    expected = s["version"] if s else 0
    action, s2 = await handle_event(deps, s, ev)
    if s2 is not None:                  # saving even an unchanged session refreshes its TTL
        await store.save(s2, expected)
    return action
