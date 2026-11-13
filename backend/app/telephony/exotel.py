"""Exotel adapter (contract C7). Owner: Darshan.

Inbound webhooks, all under /tel/exotel/{WEBHOOK_SECRET}/ (Exotel documents no signature, so the secret is in the path):
  POST|GET /missed                a farmer's missed call            -> queue a CALLBACK job. Always 200.
  GET      /gather?step=k         Gather applet k (dynamic URL)     -> JSON prompt for the current state
  GET      /digits?step=k         Passthru applet k                 -> 200 continue | 404 hang up (failure branch)
  POST     /status                StatusCallback of our outbound call -> release lock, finish or retry the job

Outbound: place_call() posts Calls/connect.json (farmer first, then the App Bazaar flow `annadata-ivr`) and remembers the
CallSid in callmap:exotel:{sid}. Inbound events are accepted ONLY for CallSids we started (403 otherwise).

Behaviour that Exotel documents ambiguously (the D7 spike with a real phone must confirm, adapt here if needed):
  - digits arrive wrapped in literal quotes ("17")        -> stripped here
  - Passthru may be GET or POST                           -> /digits and /status accept both, query or form
  - a 404 from Passthru takes the failure branch -> Hangup
Each Gather/Passthru pair uses the engine like any other adapter: one event, one Action. The Action returned by the last
transition is kept in Valkey so the next Gather replays it exactly (including "bad input" prefixes).
"""
import dataclasses
import hmac
import json
import logging
import re
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from .. import cache, db
from ..config import settings
from ..engine import flows, guard
from ..engine import session as store
from ..engine.actions import Action, Event
from ..engine.audio_shim import mix_url
from ..engine.service import mark_dropped, process
from ..services import jobs

log = logging.getLogger("exotel")
router = APIRouter(prefix="/tel/exotel/{secret}")
name = "exotel"
CALLMAP_TTL = 3600
STATE_TTL = 900


# ---------------------------------------------------------------- helpers

def _check(secret: str) -> None:
    ok = bool(settings.webhook_secret) and hmac.compare_digest(secret.encode(), settings.webhook_secret.encode())
    if not ok:
        raise HTTPException(403, detail={"error": "FORBIDDEN"})


def normalise(raw: str) -> str | None:
    """Exotel sends Indian numbers as 0XXXXXXXXXX, 91XXXXXXXXXX, +91XXXXXXXXXX or XXXXXXXXXX. Returns +91XXXXXXXXXX."""
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 10:
        d = "91" + d
    elif len(d) == 11 and d.startswith("0"):
        d = "91" + d[1:]
    return "+" + d if len(d) == 12 and d.startswith("91") else None


def normalize_e164(raw: str) -> str:
    """Strict form of normalise(): '' instead of None for anything that is not an Indian mobile number."""
    return normalise(raw) or ""


def strip_digits(raw: str) -> str:
    """Exotel wraps the collected digits in literal quotes ('"17"' -> '17') and may leave the terminator on ('15#' -> '15')."""
    return (raw or "").strip().strip('"').strip("'").strip().rstrip("#").strip()


async def _params(request: Request) -> dict:
    p = dict(request.query_params)
    if request.method == "POST":
        try:
            p.update({k: v for k, v in (await request.form()).items() if isinstance(v, str)})
        except Exception:
            pass
    return p


def _absolute(url: str) -> str:
    return url if url.startswith("http") else settings.public_base_url.rstrip("/") + url


def _gather_json(a: Action) -> dict:
    """Terminal prompts play once: the Gather waits 1 s for a key and the following Passthru ends the call."""
    closing = a.hangup or not a.max_digits
    return {"gather_prompt": {"audio_url": _absolute(mix_url(a.clips, a.lang))},
            "max_input_digits": a.max_digits or 1, "finish_on_key": a.finish_on_key or "#",
            "input_timeout": 1 if closing else a.timeout_s,
            # Exotel's default is repeat_menu=0: a farmer who has not pressed a key by the timeout is hung up on.
            # Repeating the menu twice gives people time to find the key (the closing prompt is never repeated).
            "repeat_menu": 0 if closing else 2}


async def _remember(sid: str, a: Action) -> None:
    await cache.redis.set(f"exo:act:{sid}", json.dumps(dataclasses.asdict(a)), ex=STATE_TTL)


async def _recall(sid: str) -> Action | None:
    raw = await cache.redis.get(f"exo:act:{sid}")
    return Action(**json.loads(raw)) if raw else None


async def _trace(path: str, p: dict, code: int, ms: float = 0.0, note: str = "") -> None:
    """Keep the last 300 Exotel requests (no secret, phone numbers masked) so a failed call can be read back with
    GET /api/ops/exotel-trace or scripts/exotel_trace.py."""
    try:
        def m(x: str) -> str:
            n = normalize_e164(x)
            return n[:5] + "****" + n[-3:] if n else (x[:3] + "..." if x else "")
        row = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "path": path, "sid": (p.get("CallSid") or "")[-8:],
               "step": p.get("step"), "from": m(p.get("CallFrom") or p.get("From", "")), "to": m(p.get("CallTo") or p.get("To", "")),
               "status": p.get("Status") or p.get("CallStatus"), "duration": p.get("DialCallDuration") or p.get("Duration"),
               "digits": strip_digits(p.get("digits") or p.get("Digits") or "") or None, "code": code, "ms": round(ms), "note": note or None}
        pipe = cache.redis.pipeline()
        pipe.lpush("exo:trace", json.dumps({k: v for k, v in row.items() if v not in (None, "")}))
        pipe.ltrim("exo:trace", 0, 299)
        pipe.expire("exo:trace", 86400)
        await pipe.execute()
    except Exception:
        log.debug("trace write failed", exc_info=True)


async def _identify(request: Request, sid: str, p: dict) -> tuple[str, dict | None, str]:
    """The farmer for this call: the number we saved when WE placed the call (callmap), else, when Exotel started the call
    itself or the map is gone, the number Exotel reports (CallFrom/From/CallTo/To, normalised), if that is a registered farmer
    we are allowed to call. Returns (phone, job, how)."""
    try:
        phone, job = await _callmap(sid)
        return phone, job, "callmap"
    except HTTPException:
        pass
    exophone = normalize_e164(settings.exophone)
    for key in ("CallFrom", "From", "CallTo", "To"):
        cand = normalize_e164(p.get(key, ""))
        if not cand or cand == exophone or (settings.team_phones and cand[-10:] not in settings.team_phones):
            continue
        if await request.app.state.deps.get_farmer(cand):
            await cache.redis.set(f"callmap:exotel:{sid}", cand, ex=CALLMAP_TTL)
            log.warning("call %s was not started by us: farmer taken from %s", sid[-6:], key)
            return cand, None, "fallback:" + key
    raise HTTPException(403, detail={"error": "UNKNOWN_CALL"})


async def _callmap(sid: str) -> tuple[str, dict | None]:
    phone = await cache.redis.get(f"callmap:exotel:{sid}")
    if not phone:
        raise HTTPException(403, detail={"error": "UNKNOWN_CALL"})          # we never started this call
    raw = await cache.redis.get(f"callmap:exotel:{sid}:job")
    return phone, (json.loads(raw) if raw else None)


# ---------------------------------------------------------------- outbound

def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10)


async def place_call(phone: str, job: dict) -> bool:
    """Ring the farmer, then connect the answered call to the App Bazaar flow. True if Exotel accepted the request."""
    s = settings
    if not (s.exotel_sid and s.exotel_api_key and s.exotel_api_token and s.exophone and s.exotel_app_id):
        log.error("Exotel is not fully configured (sid, key, token, ExoPhone and EXOTEL_APP_ID are needed)")
        return False
    base = s.public_base_url.rstrip("/") + f"/tel/exotel/{s.webhook_secret}"
    form = {"From": phone, "CallerId": s.exophone, "CallType": "trans", "TimeLimit": str(s.call_cap_s), "TimeOut": "30",
            "Url": f"http://my.exotel.com/{s.exotel_sid}/exoml/start_voice/{s.exotel_app_id}",
            "StatusCallback": f"{base}/status", "CustomField": job["id"]}
    url = f"https://{s.exotel_api_host}/v1/Accounts/{s.exotel_sid}/Calls/connect.json"
    try:
        async with _client() as c:
            r = await c.post(url, data=form, auth=(s.exotel_api_key, s.exotel_api_token))
        if r.status_code >= 300:
            log.error("Exotel connect refused: HTTP %s %s", r.status_code, r.text[:200])
            return False
        sid = r.json()["Call"]["Sid"]
    except Exception:
        log.exception("Exotel connect failed")
        return False
    pipe = cache.redis.pipeline()
    pipe.set(f"callmap:exotel:{sid}", phone, ex=CALLMAP_TTL)
    pipe.set(f"callmap:exotel:{sid}:job", json.dumps(job), ex=CALLMAP_TTL)
    await pipe.execute()
    await db.pool.execute("UPDATE call_jobs SET provider_call_id = $2 WHERE id = $1::uuid", job["id"], sid)
    return True


# ---------------------------------------------------------------- inbound webhooks

@router.api_route("/missed", methods=["GET", "POST"])
async def missed(secret: str, request: Request):
    _check(secret)
    p = await _params(request)
    phone = normalize_e164(p.get("From") or p.get("CallFrom") or "") or None
    sid = p.get("CallSid") or ""
    await _trace("missed", p, 200, 0, "" if phone else "unreadable number")
    try:
        if phone and sid:
            await _handle_missed(request.app.state.deps, phone, sid)
    except Exception:
        log.exception("missed-call handling failed")
    return {"ok": True}                                                       # Exotel must always get 200


async def _handle_missed(deps, phone: str, sid: str) -> None:
    verdict = await guard.accept_missed_call(phone)                            # dedupe 20 s, 3/10 min, 6/day, budget
    if verdict != "ok":
        log.info("missed call from %s not answered: %s", phone, verdict)
        return
    farmer = await deps.get_farmer(phone)
    if not farmer and not await cache.redis.set(f"unk:{phone}", "1", nx=True, ex=settings.unknown_cb_ttl_s):
        return                                       # unknown caller: one callback a day (a minute in demo mode)
    async with db.pool.acquire() as conn:
        await jobs.enqueue_callback(conn, phone, farmer["id"] if farmer else None, sid)


@router.get("/gather")
async def gather(secret: str, request: Request):
    _check(secret)
    p = await _params(request)
    t0 = time.time()
    sid, step = p.get("CallSid", ""), int(p.get("step") or 1)
    try:
        phone, job, how = await _identify(request, sid, p)
    except HTTPException:
        await _trace("gather", p, 403, (time.time() - t0) * 1000, "unknown call")
        raise
    note = "" if how == "callmap" else how
    try:
        if step == 1 and not await cache.redis.set(f"exo:started:{sid}", "1", nx=True, ex=STATE_TTL):
            a = await _recall(sid)                                             # Exotel retried the first Gather
        elif step == 1:
            a = await _start(request.app.state.deps, phone, sid, job)
        else:
            a = await _recall(sid)
            await guard.extend_lock(phone, sid)
        if a is None:                                                          # nothing to replay: rebuild from the session
            s = await store.load(phone)
            a = flows.build(s["state"], s) if s and s["state"] in flows.SPEC else Action(clips=["bye"], hangup=True)
    except Exception:
        log.exception("gather failed")                       # full traceback; the call gets a polite goodbye, never a 500
        a = Action(clips=["bye"], hangup=True)
        note = "EXCEPTION"
    ms = (time.time() - t0) * 1000
    if ms > 2000:
        log.warning("slow /gather: %.0f ms (Exotel gives up after 5 s)", ms)
    await _trace("gather", p, 200, ms, f"{note} state={a.state} hangup={a.hangup}".strip())
    return _gather_json(a)


async def _start(deps, phone: str, sid: str, job: dict | None) -> Action:
    if not await guard.acquire_lock(phone, sid):                               # farmer is already on another call
        await cache.redis.set(f"exo:busy:{sid}", "1", ex=STATE_TTL)
        a = Action(clips=["bye"], hangup=True)
    else:
        if job:
            await jobs.mark_in_call(job["id"])
        ev = Event(kind="start", call_id=sid, event_id=f"{sid}:g1", provider="exotel",
                   job=job if job and job["kind"] == "BID_OFFER" else None)
        a = await process(deps, phone, ev)
        if a.hangup_now:
            a = Action(clips=["bye"], hangup=True)
    await _remember(sid, a)
    return a


@router.get("/digits")
async def digits(secret: str, request: Request):
    _check(secret)
    p = await _params(request)
    t0 = time.time()
    sid, step = p.get("CallSid", ""), int(p.get("step") or 1)
    try:
        phone, _, how = await _identify(request, sid, p)
    except HTTPException:
        await _trace("digits", p, 403, (time.time() - t0) * 1000, "unknown call")
        raise
    seen = await cache.redis.get(f"exo:resp:{sid}:{step}")                    # a retried Passthru gets the same answer
    if seen:
        await _trace("digits", p, int(seen), (time.time() - t0) * 1000, "retry")
        return _passthru(int(seen))
    if await cache.redis.exists(f"exo:busy:{sid}"):
        await _trace("digits", p, 404, (time.time() - t0) * 1000, "farmer busy on another call")
        return _passthru(404)
    d = strip_digits(p.get("digits") or p.get("Digits") or "")             # the parameter name is not documented consistently
    try:
        a = await process(request.app.state.deps, phone,
                          Event(kind="digits" if d else "timeout", digits=d, call_id=sid, event_id=f"{sid}:d{step}",
                                provider="exotel"))
    except Exception:
        log.exception("digits failed")
        await _trace("digits", p, 404, (time.time() - t0) * 1000, "EXCEPTION")
        return _passthru(404)
    code = 404 if a.hangup_now else 200
    if code == 200:
        await _remember(sid, a)
    await cache.redis.set(f"exo:resp:{sid}:{step}", str(code), ex=STATE_TTL)
    await _trace("digits", p, code, (time.time() - t0) * 1000, ("" if how == "callmap" else how + " ") + f"-> state={a.state}")
    return _passthru(code)


def _passthru(code: int):
    if code == 200:
        return {"ok": True}
    raise HTTPException(code, detail={"ok": False})


@router.api_route("/status", methods=["GET", "POST"])
async def status(secret: str, request: Request):
    _check(secret)
    p = await _params(request)
    sid = p.get("CallSid", "")
    try:
        phone, job = await _callmap(sid)
    except HTTPException:
        await _trace("status", p, 403, 0, "unknown call")
        raise
    await _trace("status", p, 200)
    state = (p.get("Status") or p.get("CallStatus") or "").lower()
    try:
        await guard.release_lock(phone, sid)
        await mark_dropped(phone)                                              # a call cut off mid-listing resumes next time
        jid = p.get("CustomField") or (job or {}).get("id")
        if jid:
            await jobs.on_call_end(jid, answered=state == "completed")
    except Exception:
        log.exception("status handling failed")
    return {"ok": True}
