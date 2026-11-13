"""Browser-simulator adapter: WebSocket protocol C6. Owner: Darshan (Hitesh reviews).

One socket per simulated phone. The adapter collects digits (the engine only sees finished strings),
applies the 120/40 ms bounce filter, and turns engine Actions into `play` / `hangup` messages.
Reliability gates (engine/guard.py): missed-call dedupe and limits before ringing, one live call per number.

Extra server message beyond C6, ignorable by clients: {"t":"info","reason":"DUPLICATE|RATE_LIMITED|BUDGET|BUSY"}
sent when a missed call is not answered with a callback.

Outbound calls (D6): services/jobs.py asks place_call() to ring a phone for a BID_OFFER job. The browser phone gets
the same {"t":"ring"} message as for a callback, and answering starts the offer flow instead of a listing.
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
from ..services import jobs

log = logging.getLogger("sim")
router = APIRouter()
ACTIVE: dict[str, dict] = {}     # call_id -> {"phone", "state"}
LINES: dict[str, dict] = {}      # phone -> {"ws", "call_id", "incoming": {"call_id","job"} | None}


async def place_call(phone: str, job: dict) -> bool:
    """Ring a connected simulator phone for an outbound job. False if it is offline or already busy."""
    line = LINES.get(phone)
    if not line or line["call_id"] or line["incoming"]:
        return False
    call_id = f"sim-{uuid.uuid4().hex[:8]}"
    line["incoming"] = {"call_id": call_id, "job": job}
    try:
        await line["ws"].send_json({"t": "ring", "call_id": call_id})
    except Exception:
        line["incoming"] = None
        return False
    asyncio.create_task(_ring_timeout(phone, call_id, job["id"]))
    return True


async def _ring_timeout(phone: str, call_id: str, job_id: str) -> None:
    await asyncio.sleep(settings.sim_incoming_ring_s)
    line = LINES.get(phone)
    if line and line["incoming"] and line["incoming"]["call_id"] == call_id:    # nobody picked up
        line["incoming"] = None
        try:
            await line["ws"].send_json({"t": "hangup", "call_id": call_id})
        except Exception:
            pass
        await jobs.on_call_end(job_id, answered=False)


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
    line = {"ws": ws, "call_id": None, "incoming": None}
    LINES[phone] = line
    cur_job: str | None = None               # id of the outbound job this call is serving

    def set_call(cid: str | None) -> None:
        nonlocal call_id
        call_id = line["call_id"] = cid

    async def end_call() -> None:
        nonlocal act, buf, holds_lock, cur_job
        if call_id and holds_lock:
            await guard.release_lock(phone, call_id)
        ACTIVE.pop(call_id, None)
        act, buf, holds_lock = None, "", False
        set_call(None)
        if cur_job:
            jid, cur_job = cur_job, None
            await jobs.on_call_end(jid, answered=True)       # DONE if the farmer answered, else retry later

    async def run(ev: Event, event_id: str | None = None) -> None:
        """Send one event to the engine and relay the resulting Action."""
        nonlocal act, buf, seq
        seq += 1
        ev.call_id, ev.event_id, ev.provider = call_id or "", event_id or f"{call_id}:{seq}", "sim"
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
        await asyncio.sleep(random.uniform(settings.sim_ring_min, settings.sim_ring_max))
        set_call(f"sim-{uuid.uuid4().hex[:8]}")      # unique across restarts, so evt: keys never collide
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
            elif t == "answer":
                inc, job = line["incoming"], None
                if inc and msg.get("call_id") == inc["call_id"]:      # an outbound offer call is being answered
                    set_call(inc["call_id"])
                    job, line["incoming"] = inc["job"], None
                elif not (call_id and msg.get("call_id") == call_id):
                    continue
                if not await guard.acquire_lock(phone, call_id):      # another live call to this number
                    await ws.send_json({"t": "info", "reason": "BUSY"})
                    await ws.send_json({"t": "hangup", "call_id": call_id})
                    set_call(None)
                    if job:
                        await jobs.on_call_end(job["id"], answered=False)
                    continue
                holds_lock = True
                if job:
                    cur_job = job["id"]
                    await jobs.mark_in_call(cur_job)
                await run(Event(kind="start", job=job))
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
        if LINES.get(phone) is line:
            LINES.pop(phone, None)
        if line["incoming"]:                                          # socket died while an offer call was ringing
            try:
                await jobs.on_call_end(line["incoming"]["job"]["id"], answered=False)
            except Exception:
                log.exception("job cleanup failed")
            line["incoming"] = None
        if ringing and not ringing.done():
            ringing.cancel()
        if call_id:
            try:
                await mark_dropped(phone)
                await end_call()
            except Exception:
                log.exception("cleanup after socket close failed")
