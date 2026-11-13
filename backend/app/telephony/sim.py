"""Browser-simulator adapter: WebSocket protocol C6. Owner: Darshan (Hitesh reviews).

One socket per simulated phone. The adapter collects digits (the engine only sees finished strings),
applies the 120/40 ms bounce filter, and turns engine Actions into `play` / `hangup` messages.
Reliability gates (engine/guard.py): missed-call dedupe and limits before ringing, one live call per number.

Extra server message beyond C6, ignorable by clients: {"t":"info","reason":"DUPLICATE|RATE_LIMITED|BUDGET|BUSY"}
sent when a missed call is not answered with a callback.
"""
import asyncio
import logging
import random
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..engine import guard
from ..engine.actions import Action, Event
from ..engine.audio_shim import mix_url
from ..engine.debounce import Debouncer
from ..engine.service import log_dropped, mark_dropped, process

log = logging.getLogger("sim")
router = APIRouter()
ACTIVE: dict[str, dict] = {}     # call_id -> {"phone", "state"}


@router.websocket("/tel/sim/ws")
async def sim_ws(ws: WebSocket, phone: str = "+919800000001"):
    deps = ws.app.state.deps
    await ws.accept()
    call_id: str | None = None
    holds_lock = False
    deb = Debouncer()
    buf = ""
    act: Action | None = None          # the prompt the client is currently answering
    seq = 0
    ringing: asyncio.Task | None = None
    swallow: tuple[str, int] | None = None   # (terminator, ts_ms) left over after a length-triggered submit

    async def end_call() -> None:
        nonlocal call_id, act, buf, holds_lock
        if call_id and holds_lock:
            await guard.release_lock(phone, call_id)
        ACTIVE.pop(call_id, None)
        call_id, act, buf, holds_lock = None, None, "", False

    async def run(ev: Event, event_id: str | None = None) -> None:
        """Send one event to the engine and relay the resulting Action."""
        nonlocal act, buf, seq
        seq += 1
        ev.call_id, ev.event_id = call_id or "", event_id or f"{call_id}:{seq}"
        action = await process(deps, phone, ev)
        buf = ""
        if action.hangup_now:
            await ws.send_json({"t": "hangup", "call_id": call_id})
            await end_call()
            return
        act = action
        ACTIVE[call_id] = {"phone": phone, "state": action.state}
        await guard.extend_lock(phone, call_id)
        await ws.send_json({"t": "play", "call_id": call_id, "audio_url": mix_url(action.clips, action.lang),
                            "max_digits": action.max_digits, "finish_on_key": action.finish_on_key,
                            "timeout_s": action.timeout_s, "state": action.state})
        if action.hangup:
            cid = call_id
            await asyncio.sleep(settings.sim_hangup_delay)
            if call_id == cid:                                 # the user may have hung up meanwhile
                await ws.send_json({"t": "hangup", "call_id": cid})
                await end_call()

    async def ring() -> None:
        nonlocal call_id
        await asyncio.sleep(random.uniform(settings.sim_ring_min, settings.sim_ring_max))
        call_id = f"sim-{uuid.uuid4().hex[:8]}"      # unique across restarts, so evt: keys never collide
        await ws.send_json({"t": "ring", "call_id": call_id})

    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("t")
            if t == "missed_call":
                if call_id is not None or (ringing is not None and not ringing.done()):
                    continue
                verdict = await guard.accept_missed_call(phone)
                if verdict != "ok":
                    log.info("missed call from %s not answered: %s", phone, verdict)
                    await ws.send_json({"t": "info", "reason": verdict})
                    continue
                ringing = asyncio.create_task(ring())
            elif t == "answer" and call_id and msg.get("call_id") == call_id:
                if not await guard.acquire_lock(phone, call_id):      # another live call to this number
                    await ws.send_json({"t": "info", "reason": "BUSY"})
                    await ws.send_json({"t": "hangup", "call_id": call_id})
                    call_id = None
                    continue
                holds_lock = True
                await run(Event(kind="start"))
            elif t == "digit" and act and call_id and msg.get("call_id") == call_id:
                d, ts = str(msg.get("d", ""))[:1], int(msg.get("ts_ms") or time.time() * 1000)
                cseq = msg.get("seq")
                if not d:
                    continue
                if cseq is not None and await guard.is_duplicate_event(call_id, f"raw{cseq}"):
                    continue                                          # retransmitted key message
                if deb.is_bounce(d, ts):
                    await log_dropped(phone, f"{call_id}:b{cseq or ts}", act.state, d, "BOUNCE")
                    continue
                if swallow and d == swallow[0] and ts - swallow[1] < 2000:
                    swallow = None                                    # "17#": the # follows an auto-submit
                    await log_dropped(phone, f"{call_id}:t{cseq or ts}", act.state, d, "TERMINATOR_AFTER_MAX")
                    continue
                swallow = None
                if act.max_digits == 0:
                    continue
                if act.finish_on_key and d == act.finish_on_key:
                    if buf:
                        await run(Event(kind="digits", digits=buf, ts_ms=ts), f"{call_id}:k{cseq or ts}")
                    continue
                buf += d
                if len(buf) >= act.max_digits:
                    if act.finish_on_key:
                        swallow = (act.finish_on_key, ts)
                    await run(Event(kind="digits", digits=buf, ts_ms=ts), f"{call_id}:k{cseq or ts}")
            elif t == "timeout" and act and call_id and msg.get("call_id") == call_id:
                if buf and act.finish_on_key:                         # timeout ends multi-digit entry
                    await run(Event(kind="digits", digits=buf))
                else:
                    await run(Event(kind="timeout"))
            elif t == "hangup" and call_id and msg.get("call_id") == call_id:
                await mark_dropped(phone)                             # session stays so the next call resumes
                await end_call()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if ringing and not ringing.done():
            ringing.cancel()
        if call_id:
            try:
                await mark_dropped(phone)
                await end_call()
            except Exception:
                log.exception("cleanup after socket close failed")
