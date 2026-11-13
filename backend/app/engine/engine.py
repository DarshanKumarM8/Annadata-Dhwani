"""Call engine: one transition function for every adapter. Owner: Darshan.

handle_event(deps, session, event) -> (Action, session)

The session is a plain dict (JSON-serialisable, stored in Valkey by engine/session.py). `deps` supplies
everything that touches the outside world, so the state machine can be tested without a database.
Rules implemented here (plan section 5.4): retries max 2 then BYE, '#'/timeout ends multi-digit entry,
only an explicit 1 in FINAL commits, 240 s call cap, resume after QTY.
"""
import logging
import uuid
from datetime import date

from . import flows
from .actions import Action, Event
from .flows import GUARD_FACTOR, RESUMABLE, TERMINAL

log = logging.getLogger("engine")
MAX_RETRIES = 2
FAIL_TICKET_THRESHOLD = 3


class ListingExists(Exception):
    """The farmer already has a live listing for this crop."""


# ---------------------------------------------------------------- helpers

def new_session(phone: str, provider: str, call_id: str, now: float) -> dict:
    return {"id": str(uuid.uuid4()), "phone": phone, "farmer_id": None, "kind": "LISTING",
            "provider": provider, "call_id": call_id, "state": "", "data": {}, "version": 0,
            "retries": 0, "lang": "kn", "started_at": now, "district_code": None}


async def _enter(deps, s: dict, state: str, prefix: list[str] | None = None) -> Action:
    """Move to `state`, prepare its data, and return the prompt."""
    s["state"], s["retries"] = state, 0
    d = s["data"]
    if state == "CROP":
        d["menu"] = await deps.crop_menu(s["district_code"], date.today().month)
    elif state == "PRICE":
        d["floor"] = await deps.get_floor(s["district_code"], d["crop"])
    elif state in ("HELP", "NOT_REGISTERED"):
        reason = "UNKNOWN_CALLER" if state == "NOT_REGISTERED" else d.get("help_reason", "HELP_KEY")
        d["verbal_code"] = await deps.open_ticket(s["phone"], s["farmer_id"], reason)
    return flows.build(state, s, prefix)


async def _home(deps, s: dict, prefix: list[str] | None = None) -> Action:
    live = await deps.has_any_live_listing(s["farmer_id"])
    return await _enter(deps, s, "MAIN" if live else "CROP", prefix)


# ---------------------------------------------------------------- start

async def _start_offer(deps, ev: Event) -> tuple[Action, dict | None]:
    """Outbound BID_OFFER call: read the offer to the farmer whose lot is in the winning bid."""
    p = ev.job["payload"]
    offer = await deps.get_offer(p["bid_id"], p["listing_id"])
    if not offer:                                  # round already settled, or already answered
        return Action(hangup_now=True), None
    s = new_session(ev.phone, deps.provider, ev.call_id, deps.now())
    s.update(kind="BID_OFFER", farmer_id=offer["farmer_id"], district_code=offer["district_code"],
             lang=offer["lang"] or "kn")
    s["data"] = {"bid_id": p["bid_id"], "listing_id": p["listing_id"], "job_id": ev.job.get("id"),
                 "offer": {k: offer[k] for k in ("price", "qty", "crop", "ask")}}
    return await _enter(deps, s, "OFFER"), s


async def _start(deps, s: dict | None, ev: Event) -> tuple[Action, dict | None]:
    now = deps.now()
    if ev.job and ev.job.get("kind") == "BID_OFFER":
        return await _start_offer(deps, ev)
    if s and s["state"] not in TERMINAL and s["state"] in RESUMABLE:
        s.update(call_id=ev.call_id, started_at=now, retries=0)
        return flows.build(s["state"], s, ["welcome_back"]), s

    f = await deps.get_farmer(ev.phone)
    s = new_session(ev.phone, deps.provider, ev.call_id, now)
    if not f:
        s["kind"] = "UNKNOWN_CALLER"
        return await _enter(deps, s, "NOT_REGISTERED"), s
    s.update(farmer_id=f["id"], district_code=f["district_code"], lang=f["lang"] or "kn")
    s["data"]["consented"] = bool(f["consented"])
    if not f["lang"]:
        return await _enter(deps, s, "LANG"), s
    if not f["consented"]:
        return await _enter(deps, s, "CONSENT"), s
    return await _home(deps, s), s


# ---------------------------------------------------------------- input handling

async def _retry(deps, s: dict, invalid: bool) -> Action:
    s["retries"] += 1
    if s["retries"] > MAX_RETRIES:
        s["data"]["failed_input"] = True
        if s["kind"] == "BID_OFFER":             # nothing recorded: the job queue calls again
            return await _enter(deps, s, "BYE")
        if await deps.record_failure(s["phone"]) >= FAIL_TICKET_THRESHOLD:   # 3 failed calls in 24 h: get a human
            s["data"]["help_reason"] = "IVR_FAIL_3"
            return await _enter(deps, s, "HELP")
        return await _enter(deps, s, "BYE")
    return flows.build(s["state"], s, ["bad_input"] if invalid else None)


async def _answer(deps, s: dict, response: str) -> bool:
    """Record the farmer's ACCEPT/REJECT (first answer wins). False if it could not be stored."""
    d = s["data"]
    try:
        await deps.record_offer_response(d["bid_id"], d["listing_id"], response)
        return True
    except Exception:
        log.exception("record_offer_response failed")
        return False


async def _apply(deps, s: dict, digits: str) -> Action | None:
    """Return the next Action, or None when the input is invalid for this state."""
    st, d = s["state"], s["data"]
    one = digits if len(digits) == 1 else ""

    if st == "LANG":
        if one not in ("1", "2"):
            return None
        s["lang"] = "kn" if one == "1" else "hi"
        await deps.set_lang(s["farmer_id"], s["lang"])
        return await (_enter(deps, s, "CONSENT") if not d.get("consented") else _home(deps, s))

    if st == "CONSENT":
        if one not in ("1", "2"):
            return None
        await deps.record_consent(s["farmer_id"], s["id"], s["lang"], one)
        if one == "2":
            return await _enter(deps, s, "BYE")
        d["consented"] = True
        return await _home(deps, s)

    if st == "MAIN":
        if one == "1":
            return await _enter(deps, s, "CROP")
        if one == "0":
            return await _enter(deps, s, "HELP")
        return None

    if st == "CROP":
        if one == "0":
            return await _enter(deps, s, "HELP")
        menu = d.get("menu", [])
        if not (one.isdigit() and 1 <= int(one) <= len(menu)):
            return None
        crop = menu[int(one) - 1]
        if await deps.has_live_listing(s["farmer_id"], crop):
            return await _enter(deps, s, "MAIN", ["already_listed"])
        d["crop"] = crop
        d["crop_info"] = await deps.get_crop(crop)
        return await _enter(deps, s, "QTY")

    if st == "QTY":
        if not digits.isdigit():
            return None
        n = int(digits)
        cap = min(int(d["crop_info"]["max_listing_qtl"]), 50)   # qty_1..qty_50 are the recorded clips
        if not 1 <= n <= cap:
            return None
        d["qty"] = n
        return await _enter(deps, s, "QTY_CONFIRM")

    if st == "QTY_CONFIRM":
        if one == "1":
            return await _enter(deps, s, "PRICE")
        if one == "2":
            d.pop("qty", None)
            return await _enter(deps, s, "QTY")
        return None

    if st == "PRICE":
        if not digits.isdigit():
            return None
        p, ci = int(digits), d["crop_info"]
        if not float(ci["min_price"]) <= p <= float(ci["max_price"]):
            return None
        d["price"] = p
        floor = d.get("floor")
        if not floor:
            d["guardrail"] = "NO_PRICE_DATA"
            return await _enter(deps, s, "FINAL")
        if p < floor["afpp"] * GUARD_FACTOR:
            return await _enter(deps, s, "GUARD")
        d["guardrail"] = "NONE"
        return await _enter(deps, s, "FINAL")

    if st == "GUARD":
        if one == "1":
            d["price"], d["guardrail"] = int(d["floor"]["afpp"]), "RAISED"
            return await _enter(deps, s, "FINAL")
        if one == "2":
            d["guardrail"] = "KEPT_BELOW"
            return await _enter(deps, s, "FINAL")
        if one == "3":
            return await _enter(deps, s, "PRICE")
        return None

    if st == "OFFER":
        if one == "1":
            return await _enter(deps, s, "OFFER_CONFIRM")
        if one == "9":
            return await _enter(deps, s, "OFFER")
        if one == "2":
            if not await _answer(deps, s, "REJECT"):
                return await _enter(deps, s, "BYE")
            d["offer_rejected"] = True
            return await _enter(deps, s, "BYE")
        return None

    if st == "OFFER_CONFIRM":              # only an explicit 1 here binds the farmer
        if one == "1":
            if not await _answer(deps, s, "ACCEPT"):
                return await _enter(deps, s, "BYE")
            return await _enter(deps, s, "DONE_OFFER")
        if one == "2":
            return await _enter(deps, s, "OFFER")
        return None

    if st == "FINAL":
        if one == "2":
            for k in ("crop", "crop_info", "qty", "price", "guardrail"):
                d.pop(k, None)
            return await _enter(deps, s, "CROP")
        if one != "1":
            return None
        try:                                   # the only place a listing is created
            d["code"] = await deps.commit_listing(s)
        except ListingExists:
            return await _enter(deps, s, "MAIN", ["already_listed"])
        except Exception:
            log.exception("commit_listing failed")
            return await _enter(deps, s, "BYE")
        return await _enter(deps, s, "DONE")

    return None


# ---------------------------------------------------------------- entry point

async def handle_event(deps, s: dict | None, ev: Event) -> tuple[Action, dict | None]:
    if ev.kind == "start":
        return await _start(deps, s, ev)
    if s is None or ev.kind == "hangup" or s["state"] in TERMINAL:
        return Action(hangup_now=True), s
    if deps.now() - s["started_at"] > deps.call_cap_s:       # session stays, so the next call resumes
        return Action(clips=["bye"], lang=s["lang"], state=s["state"], hangup=True), s

    if ev.kind == "timeout" or not ev.digits:
        return await _retry(deps, s, invalid=False), s
    action = await _apply(deps, s, ev.digits)
    if action is None:
        return await _retry(deps, s, invalid=True), s
    return action, s
