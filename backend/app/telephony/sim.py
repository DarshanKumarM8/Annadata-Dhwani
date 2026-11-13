"""Browser-simulator adapter: WebSocket protocol C6. Owner: Darshan (Hitesh reviews).

One socket per simulated phone. The adapter collects digits (the engine only sees finished strings),
applies the 120/40 ms bounce filter, and turns engine Actions into `play` / `hangup` messages.
"""
import asyncio
import logging
import random
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..engine.actions import Action, Event
from ..engine.audio_shim import mix_url
from ..engine.debounce import Debouncer
from ..engine.service import process

log = logging.getLogger("sim")
router = APIRouter()
_call_no = 0
ACTIVE: dict[str, dict] = {}     # call_id -> {"phone", "state"} (read by the ops page in D5)
DTMF_LOG: list[dict] = []        # recent dropped/accepted presses; D3 persists these to dtmf_events


def _log_dtmf(call_id: str, state: str, digits: str, dropped: str | None) -> None:
    DTMF_LOG.append({"session_id": call_id, "state_before": state, "digits": digits, "state_after": state,
                     "dropped_reason": dropped, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    del DTMF_LOG[:-200]


@router.websocket("/tel/sim/ws")
async def sim_ws(ws: WebSocket, phone: str = "+919800000001"):
    deps = ws.app.state.deps
    await ws.accept()
    call_id: str | None = None
    deb = Debouncer()
    buf = ""
    act: Action | None = None          # the prompt the client is currently answering
    seq = 0
    ringing: asyncio.Task | None = None
    swallow: tuple[str, int] | None = None   # (terminator, ts_ms) left over after a length-triggered submit

    async def run(ev: Event) -> None:
        """Send one event to the engine and relay the resulting Action."""
        nonlocal act, buf, call_id, seq
        seq += 1
        ev.call_id, ev.event_id = call_id or "", f"{call_id}:{seq}"
        action = await process(deps, phone, ev)
        buf = ""
        if action.hangup_now:
            await ws.send_json({"t": "hangup", "call_id": call_id})
            ACTIVE.pop(call_id, None)
            call_id = None
            return
        act = action
        ACTIVE[call_id] = {"phone": phone, "state": action.state}
        await ws.send_json({"t": "play", "call_id": call_id, "audio_url": mix_url(action.clips, action.lang),
                            "max_digits": action.max_digits, "finish_on_key": action.finish_on_key,
                            "timeout_s": action.timeout_s, "state": action.state})
        if action.hangup:
            cid = call_id
            await asyncio.sleep(settings.sim_hangup_delay)
            if call_id == cid:                                 # the user may have hung up meanwhile
                await ws.send_json({"t": "hangup", "call_id": cid})
                ACTIVE.pop(cid, None)
                call_id = None

    async def ring() -> None:
        nonlocal call_id
        global _call_no
        await asyncio.sleep(random.uniform(settings.sim_ring_min, settings.sim_ring_max))
        _call_no += 1
        call_id = f"sim-{_call_no}"
        await ws.send_json({"t": "ring", "call_id": call_id})

    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("t")
            if t == "missed_call":
                if call_id is None and (ringing is None or ringing.done()):
                    ringing = asyncio.create_task(ring())
            elif t == "answer" and call_id and msg.get("call_id") == call_id:
                await run(Event(kind="start"))
            elif t == "digit" and act and call_id and msg.get("call_id") == call_id:
                d, ts = str(msg.get("d", ""))[:1], int(msg.get("ts_ms") or time.time() * 1000)
                if not d:
                    continue
                if deb.is_bounce(d, ts):
                    _log_dtmf(call_id, act.state, d, "BOUNCE")
                    continue
                if swallow and d == swallow[0] and ts - swallow[1] < 2000:
                    swallow = None                             # "17#": the # arrives after 2 digits already submitted
                    _log_dtmf(call_id, act.state, d, "TERMINATOR_AFTER_MAX")
                    continue
                swallow = None
                _log_dtmf(call_id, act.state, d, None)
                if act.max_digits == 0:
                    continue
                if act.finish_on_key and d == act.finish_on_key:
                    if buf:
                        await run(Event(kind="digits", digits=buf, ts_ms=ts))
                    continue
                buf += d
                if len(buf) >= act.max_digits:
                    if act.finish_on_key:
                        swallow = (act.finish_on_key, ts)
                    await run(Event(kind="digits", digits=buf, ts_ms=ts))
            elif t == "timeout" and act and call_id and msg.get("call_id") == call_id:
                if buf and act.finish_on_key:                  # timeout ends multi-digit entry
                    await run(Event(kind="digits", digits=buf))
                else:
                    await run(Event(kind="timeout"))
            elif t == "hangup" and call_id and msg.get("call_id") == call_id:
                ACTIVE.pop(call_id, None)                      # session stays in Valkey so the next call resumes
                call_id, act, buf = None, None, ""
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if ringing and not ringing.done():
            ringing.cancel()
        ACTIVE.pop(call_id, None) if call_id else None
