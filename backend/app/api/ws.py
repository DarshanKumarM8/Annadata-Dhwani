"""Dashboard WebSocket hub (contract C5). Owner: Darshan.

/ws?token=<jwt>&since=<seq>
  - replays events with seq > since (at most 500; more than that -> {"type":"resync"} and the client refetches REST)
  - then streams live. Wake-up is Redis pub/sub on ad:events; a 2 s poll of the events table is the fallback, so a
    lost publish or a Valkey flush only costs up to 2 seconds.
  - audience filter: anonymous sees 'all'; buyer 'all'+'buyer'; agent 'all'+'agent'; admin sees everything.
  - messages are {"seq","type","payload"}. Delivery is at-least-once; clients drop a seq they have seen.
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import cache, db
from ..services.events import CHANNEL
from .auth import decode

log = logging.getLogger("ws")
router = APIRouter()
REPLAY_MAX = 500
POLL_S = 2.0

VISIBLE = {None: {"all"}, "buyer": {"all", "buyer"}, "agent": {"all", "agent"},
           "admin": {"all", "buyer", "agent", "ops"}}


class Hub:
    def __init__(self) -> None:
        self.conns: dict[asyncio.Queue, str | None] = {}
        self.last = 0

    async def run(self) -> None:
        """Single fan-out loop: wake on pub/sub or every POLL_S, read new rows, push to every connection."""
        self.last = await db.pool.fetchval("SELECT COALESCE(MAX(seq), 0) FROM events")
        pubsub = None
        while True:
            try:
                if pubsub is None:
                    pubsub = cache.redis.pubsub()
                    await pubsub.subscribe(CHANNEL)
                await pubsub.get_message(ignore_subscribe_messages=True, timeout=POLL_S)
            except asyncio.CancelledError:
                raise
            except Exception:
                pubsub = None                                  # Valkey down or flushed: poll only
                await asyncio.sleep(POLL_S)
            try:
                await self.drain()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("hub poll failed")

    async def drain(self) -> None:
        while True:
            rows = await db.pool.fetch(
                "SELECT seq, type, audience, payload FROM events WHERE seq > $1 ORDER BY seq LIMIT 500", self.last)
            for r in rows:
                self.last = r["seq"]
                for q, role in list(self.conns.items()):
                    if r["audience"] in VISIBLE.get(role, {"all"}):
                        try:
                            q.put_nowait({"seq": r["seq"], "type": r["type"], "payload": r["payload"]})
                        except asyncio.QueueFull:
                            q.put_nowait(None)                 # slow client: drop it, it reconnects with since
            if len(rows) < 500:
                return


hub = Hub()


@router.websocket("/ws")
async def ws(websocket: WebSocket, token: str | None = None, since: int = 0):
    await websocket.accept()
    claims = decode(token)
    role = claims["role"] if claims else None
    allowed = VISIBLE.get(role, {"all"})
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    hub.conns[q] = role                                         # register first, so nothing falls in a gap
    sent = since
    try:
        rows = await db.pool.fetch(
            "SELECT seq, type, audience, payload FROM events WHERE seq > $1 ORDER BY seq LIMIT $2",
            since, REPLAY_MAX + 1)
        newest = await db.pool.fetchval("SELECT COALESCE(MAX(seq), 0) FROM events")
        if len(rows) > REPLAY_MAX or since > newest:       # too far behind, or ahead (database was reset)
            await websocket.send_json({"type": "resync"})
            sent = newest
        else:
            for r in rows:
                sent = r["seq"]
                if r["audience"] in allowed:
                    await websocket.send_json({"seq": r["seq"], "type": r["type"], "payload": r["payload"]})
        while True:
            m = await q.get()
            if m is None:
                break
            if m["seq"] > sent:
                sent = m["seq"]
                await websocket.send_json(m)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.conns.pop(q, None)
