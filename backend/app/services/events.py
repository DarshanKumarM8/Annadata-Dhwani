"""Events outbox (contract C5). Owner: Darshan.

emit() inserts the event on the SAME connection/transaction as the change, so an event exists if and only if the
change committed. publish() is called after commit and only wakes the WebSocket hub; if it is lost the hub's 2 s
poll still finds the row. Delivery to clients is at-least-once and ordered by seq.
"""
import logging

from .. import cache

log = logging.getLogger("events")
CHANNEL = "ad:events"


async def emit(conn, type_: str, payload: dict, audience: str = "all") -> int:
    return await conn.fetchval("INSERT INTO events (type, audience, payload) VALUES ($1, $2, $3) RETURNING seq",
                               type_, audience, payload)


async def publish(seqs) -> None:
    """Call after the transaction committed. Never raises."""
    if not seqs:
        return
    try:
        await cache.redis.publish(CHANNEL, str(max(seqs)))
    except Exception:
        log.warning("publish failed; the hub poll will deliver")
