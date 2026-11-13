"""Mock backend for frontend work before the real backend is ready (TASK_DIVISION.md §3, C11).

Run from the repo root:
    pip install -r mock/requirements.txt
    python mock/mock_server.py            # http://localhost:8001  (ws://localhost:8001)

It serves every C4 endpoint from contracts/fixtures, the C5 dashboard WebSocket with a scripted
story, and the C6 simulator-phone WebSocket with a scripted IVR call. State is in memory and resets
on restart. Owner: Darshan. Do not change response shapes without changing the contract.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import random
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, Header, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "contracts" / "fixtures"
PORT = int(os.environ.get("MOCK_PORT", "8001"))
STORY_INTERVAL_S = float(os.environ.get("MOCK_STORY_INTERVAL", "5"))


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


app = FastAPI(title="Annadata Dhwani mock server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["*"])


def err(status: int, code: str, **extra):
    return JSONResponse({"error": code, **extra}, status_code=status)


# ---------------- in-memory state ----------------
class State:
    def __init__(self):
        self.clusters = {c["id"]: c for c in load("clusters.json")["clusters"]}
        self.detail = load("cluster_detail.json")
        self.bids = load("bids_mine.json")["bids"]
        self.deals = load("deals_mine.json")["deals"]
        self.tasks = load("agent_tasks.json")
        self.idem: dict[str, dict] = {}            # Idempotency-Key -> bid response
        self.verified: set[str] = set()
        self.codes_used: set[str] = set()
        self.events: list[dict] = []                # {"seq","type","audience","payload"}
        self.seq = 0
        self.listeners: set[asyncio.Queue] = set()

    def emit(self, type_: str, payload: dict, audience: str = "all"):
        self.seq += 1
        ev = {"seq": self.seq, "type": type_, "audience": audience, "payload": payload}
        self.events.append(ev)
        self.events = self.events[-2000:]
        for q in list(self.listeners):
            q.put_nowait(ev)
        if type_ == "cluster.updated":
            self.clusters[payload["id"]] = payload


S = State()


def role_of(auth: str | None) -> str:
    # Mock tokens look like "mock-<role>-<n>". Missing token = buyer, to keep frontend work easy.
    if auth and auth.startswith("Bearer mock-"):
        return auth.split("-")[1]
    return "buyer"


# ---------------- auth ----------------
@app.post("/api/auth/buyer/login")
async def buyer_login(body: dict):
    email = body.get("email", "buyer1@demo.test")
    if not body.get("password"):
        return err(401, "BAD_CREDENTIALS")
    role = "admin" if email.startswith("admin@") else "buyer"
    return {"token": f"mock-{role}-{random.randint(1000, 9999)}",
            "buyer": {"id": "60000000-0000-4000-8000-000000000001",
                      "org_name": "Admin" if role == "admin" else "Mysuru Grain Traders", "status": "APPROVED"}}


@app.post("/api/auth/agent/login")
async def agent_login(body: dict):
    if not body.get("phone") or not body.get("pin"):
        return err(401, "BAD_CREDENTIALS")
    return {"token": f"mock-agent-{random.randint(1000, 9999)}",
            "agent": {"id": "70000000-0000-4000-8000-000000000101", "name": "Kavya",
                      "fpo_id": "80000000-0000-4000-8000-000000000001"}}


# ---------------- buyer ----------------
@app.get("/api/clusters")
async def clusters(status: str | None = None, crop: str | None = None):
    items = list(S.clusters.values())
    if status:
        wanted = set(status.split(","))
        items = [c for c in items if c["status"] in wanted]
    if crop:
        items = [c for c in items if c["crop_code"] == crop]
    return {"clusters": sorted(items, key=lambda c: c["code"])}


@app.get("/api/clusters/{cid}")
async def cluster(cid: str):
    c = S.clusters.get(cid)
    if not c:
        return err(404, "NOT_FOUND")
    d = S.detail.get(cid, {"lots": [], "price_ref": None, "msp": None})
    return {**c, **d}


@app.post("/api/clusters/{cid}/bids")
async def place_bid(cid: str, body: dict, idempotency_key: str | None = Header(default=None)):
    if not idempotency_key:
        return err(400, "IDEMPOTENCY_KEY_REQUIRED")
    if idempotency_key in S.idem:
        return JSONResponse(S.idem[idempotency_key], status_code=200)
    c = S.clusters.get(cid)
    if not c:
        return err(404, "NOT_FOUND")
    if c["status"] != "BIDDING":
        return err(409, "CLUSTER_NOT_BIDDING")
    price = float(body.get("price_per_qtl", 0))
    min_qty = float(body.get("min_qty_qtl", 0))
    best = (c.get("best_bid") or {}).get("price_per_qtl")
    floor = max(c.get("min_ask") or 0, (best + 10) if best else 0)
    if price < floor:
        return err(409, "BID_TOO_LOW", min_next=floor)
    if min_qty <= 0 or min_qty > c["total_qtl"]:
        return err(422, "MIN_QTY_TOO_HIGH")
    await asyncio.sleep(0.3)  # makes double-click bugs visible
    bid = {"id": f"10000000-0000-4000-8000-{random.randint(10**11, 10**12 - 1)}", "status": "LEADING",
           "price_per_qtl": price, "min_qty_qtl": min_qty}
    S.idem[idempotency_key] = bid
    S.bids.insert(0, {**bid, "cluster_id": cid, "progress": None})
    nc = copy.deepcopy(c)
    nc["best_bid"] = {"price_per_qtl": price, "mine": True}
    nc["version"] += 1
    S.emit("bid.placed", {"cluster_id": cid, "bid_id": bid["id"], "price_per_qtl": price, "buyer_is_you": True},
           "buyer")
    S.emit("cluster.updated", nc)
    return JSONResponse(bid, status_code=201)


@app.get("/api/bids/mine")
async def bids_mine():
    return {"bids": S.bids}


@app.get("/api/deals/mine")
async def deals_mine():
    return {"deals": S.deals}


@app.post("/api/deals/{did}/payment-reported")
async def payment_reported(did: str, body: dict):
    for d in S.deals:
        if d["id"] == did:
            if not body.get("payment_ref"):
                return err(422, "PAYMENT_REF_REQUIRED")
            d["status"] = "PAYMENT_REPORTED"
            S.emit("deal.updated", {"deal_id": did, "status": "PAYMENT_REPORTED"}, "buyer")
            return {"status": "PAYMENT_REPORTED"}
    return err(404, "NOT_FOUND")


# ---------------- agent ----------------
@app.get("/api/agent/tasks")
async def agent_tasks():
    t = copy.deepcopy(S.tasks)
    t["verify"] = [c for c in t["verify"] if c["id"] not in S.verified]
    return t


@app.post("/api/agent/clusters/{cid}/verification")
async def verification(cid: str, photo: UploadFile = File(...), grade: str = Form(...),
                       lat: float = Form(...), lon: float = Form(...), accuracy_m: float = Form(...),
                       captured_at: str = Form(...), moisture_pct: float | None = Form(default=None)):
    if cid in S.verified:
        return err(409, "ALREADY_VERIFIED")
    if grade not in ("A", "B", "C", "REJECT"):
        return err(422, "BAD_GRADE")
    if lat == 0 or lon == 0:
        return err(422, "TOO_FAR", distance_m=1840)
    if accuracy_m > 200:
        return err(422, "LOW_ACCURACY")
    await photo.read()
    S.verified.add(cid)
    ends = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 180))
    c = S.clusters.get(cid)
    if c:
        nc = copy.deepcopy(c)
        nc.update(status="BIDDING" if grade != "REJECT" else "OPEN", grade=None if grade == "REJECT" else grade,
                  photo_url="/media/v/sample.svg", bidding_ends_at=ends, version=c["version"] + 1)
        S.emit("cluster.updated", nc)
    return JSONResponse({"cluster_id": cid, "status": "BIDDING" if grade != "REJECT" else "OPEN",
                         "bidding_ends_at": ends}, status_code=201)


@app.post("/api/agent/triage/{tid}/claim")
async def triage_claim(tid: str):
    for t in S.tasks["tickets"]:
        if t["id"] == tid:
            t["status"] = "ASSIGNED"
            return {"status": "ASSIGNED"}
    return err(404, "NOT_FOUND")


@app.post("/api/agent/triage/{tid}/bridge")
async def triage_bridge(tid: str):
    if tid in S.codes_used:
        return err(409, "CODE_USED")
    S.codes_used.add(tid)
    return {"verbal_code": "55", "mode": "simulated"}


@app.post("/api/agent/deals/{did}/payment-confirmed")
async def payment_confirmed(did: str):
    for d in S.tasks["deals"]:
        if d["id"] == did:
            d["status"] = "PAID"
    for d in S.deals:
        if d["id"] == did:
            d["status"] = "PAID"
    S.emit("deal.updated", {"deal_id": did, "status": "PAID"}, "buyer")
    return {"status": "PAID"}


# ---------------- admin / ops ----------------
@app.post("/api/admin/clusters/{cid}/close-auction")
async def close_auction(cid: str):
    c = S.clusters.get(cid)
    if not c:
        return err(404, "NOT_FOUND")
    nc = copy.deepcopy(c)
    nc.update(status="CONFIRMING", version=c["version"] + 1)
    S.emit("cluster.updated", nc)
    return {"status": "CONFIRMING"}


@app.post("/api/admin/prices/refresh")
async def prices_refresh():
    return {"floors_written": 6}


@app.get("/api/ops/calls")
async def ops_calls():
    d = load("ops_calls.json")
    for s in d["sessions"]:
        s["version"] += int(time.time() / 3) % 5  # makes the "version changed" highlight visible
    for sim in SIM_CALLS.values():
        d["sessions"].insert(0, {"phone_masked": "+91•••••" + sim["phone"][-4:], "kind": "LISTING",
                                 "state": sim["state"], "provider": "sim", "version": sim["version"],
                                 "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return d


@app.get("/api/ops/dtmf")
async def ops_dtmf(limit: int = 50):
    return {"events": (SIM_DTMF[::-1] + load("ops_dtmf.json")["events"])[:limit]}


@app.post("/api/ops/chaos/flush-redis")
async def flush_redis():
    return {"ok": True}


@app.get("/health")
async def health():
    return load("health.json")


# ---------------- static ----------------
@app.get("/audio/mix/{name}")
async def audio(name: str):
    return FileResponse(FIX / "sample.wav", media_type="audio/wav")


@app.get("/media/v/{name}")
async def media(name: str):
    return FileResponse(FIX / "sample.svg", media_type="image/svg+xml")


# ---------------- C5 dashboard WebSocket ----------------
@app.websocket("/ws")
async def ws(websocket: WebSocket, token: str | None = None, since: int = 0):
    await websocket.accept()
    role = role_of(f"Bearer {token}" if token else None)
    q: asyncio.Queue = asyncio.Queue()
    S.listeners.add(q)

    def visible(ev):
        a = ev["audience"]
        return a == "all" or a == role or role == "admin" or (a == "buyer" and role == "buyer")

    try:
        backlog = [e for e in S.events if e["seq"] > since]
        if since and S.events and since < S.events[0]["seq"] - 1 or len(backlog) > 500:
            await websocket.send_json({"type": "resync"})
        else:
            for e in backlog:
                if visible(e):
                    await websocket.send_json({k: e[k] for k in ("seq", "type", "payload")})
        while True:
            e = await q.get()
            if visible(e):
                await websocket.send_json({k: e[k] for k in ("seq", "type", "payload")})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        S.listeners.discard(q)


async def story_loop():
    story = load("events_story.json")
    while True:
        for ev in story:
            await asyncio.sleep(STORY_INTERVAL_S)
            S.emit(ev["type"], copy.deepcopy(ev["payload"]), ev["audience"])
        await asyncio.sleep(STORY_INTERVAL_S)
        # reset cluster 101 so the story can repeat
        S.emit("cluster.updated", {**load("clusters.json")["clusters"][0], "version": 1000 + S.seq})


# ---------------- C6 simulator phone WebSocket ----------------
# Scripted call: (state, max_digits, finish_on_key, timeout_s). Any valid input moves to the next state.
SCRIPT = [("LANG", 1, "", 6), ("CONSENT", 1, "", 8), ("CROP", 1, "", 6), ("QTY", 2, "#", 8),
          ("QTY_CONFIRM", 1, "", 6), ("PRICE", 5, "#", 10), ("GUARD", 1, "", 8), ("FINAL", 1, "", 8),
          ("DONE", 0, "", 0)]
SIM_CALLS: dict[str, dict] = {}   # call_id -> call
SIM_DTMF: list[dict] = []
_call_no = 0


@app.websocket("/tel/sim/ws")
async def sim_ws(websocket: WebSocket, phone: str = "+919800000001"):
    global _call_no
    await websocket.accept()
    call: dict | None = None

    async def play(c):
        state, maxd, fin, to = SCRIPT[c["step"]]
        c["state"], c["buf"] = state, ""
        c["version"] += 1
        await websocket.send_json({"t": "play", "call_id": c["id"], "audio_url": f"/audio/mix/{state.lower()}.wav",
                                   "max_digits": maxd, "finish_on_key": fin, "timeout_s": to, "state": state})
        if state == "DONE":
            await asyncio.sleep(1.5)
            await websocket.send_json({"t": "hangup", "call_id": c["id"]})
            SIM_CALLS.pop(c["id"], None)

    async def submit(c, digits: str):
        state = SCRIPT[c["step"]][0]
        SIM_DTMF.append({"session_id": c["id"], "state_before": state, "digits": digits,
                         "state_after": SCRIPT[c["step"] + 1][0], "dropped_reason": None,
                         "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        del SIM_DTMF[:-200]
        c["step"] += 1
        await play(c)

    try:
        while True:
            msg = await websocket.receive_json()
            t = msg.get("t")
            if t == "missed_call" and call is None:
                _call_no += 1
                call = {"id": f"sim-{_call_no}", "phone": phone, "step": 0, "state": "RINGING", "buf": "",
                        "version": 0, "last": None}
                SIM_CALLS[call["id"]] = call
                await asyncio.sleep(random.uniform(1, 3))
                await websocket.send_json({"t": "ring", "call_id": call["id"]})
            elif t == "answer" and call and msg.get("call_id") == call["id"]:
                await play(call)
            elif t == "digit" and call and msg.get("call_id") == call["id"]:
                d, ts = str(msg.get("d", "")), int(msg.get("ts_ms", 0))
                last = call["last"]
                call["last"] = (d, ts)
                if last and ((last[0] == d and ts - last[1] < 120) or ts - last[1] < 40):
                    SIM_DTMF.append({"session_id": call["id"], "state_before": call["state"], "digits": d,
                                     "state_after": call["state"], "dropped_reason": "BOUNCE",
                                     "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                    continue
                _, maxd, fin, _ = SCRIPT[call["step"]]
                if maxd == 0:
                    continue
                if fin and d == fin:
                    if call["buf"]:
                        await submit(call, call["buf"])
                    continue
                call["buf"] += d
                if len(call["buf"]) >= maxd:
                    await submit(call, call["buf"])
            elif t == "timeout" and call and msg.get("call_id") == call["id"]:
                if call["buf"] and SCRIPT[call["step"]][2]:
                    await submit(call, call["buf"])     # timeout ends multi-digit entry
                else:
                    await play(call)                    # replay the prompt
            elif t == "hangup" and call:
                SIM_CALLS.pop(call["id"], None)
                call = None
            if call and call["id"] not in SIM_CALLS:
                call = None                             # finished (DONE)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if call:
            SIM_CALLS.pop(call["id"], None)


@app.on_event("startup")
async def _start():
    asyncio.create_task(story_loop())


@app.get("/")
async def index(request: Request):
    return {"mock": True, "docs": "/docs", "ws": ["/ws", "/tel/sim/ws?phone=%2B919800000001"]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
