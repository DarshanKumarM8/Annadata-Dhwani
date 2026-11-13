"""Smoke test for the mock server's two WebSockets (C5, C6). Run while mock_server.py is up:
    python mock/smoke_test.py
Needs: pip install websockets"""
import asyncio
import json
import time

import websockets

BASE = "ws://localhost:8001"


async def dashboard():
    seen = []
    async with websockets.connect(f"{BASE}/ws?token=mock-buyer-1&since=0") as ws:
        for _ in range(4):
            seen.append(json.loads(await asyncio.wait_for(ws.recv(), 15)))
    last = seen[-1]["seq"]
    # reconnect with since=last: nothing older than last may arrive
    async with websockets.connect(f"{BASE}/ws?token=mock-buyer-1&since={last}") as ws:
        nxt = json.loads(await asyncio.wait_for(ws.recv(), 15))
    assert nxt.get("type") == "resync" or nxt["seq"] > last, nxt
    print("dashboard ws OK:", [e["type"] for e in seen], "-> replay after", last, "gave seq", nxt.get("seq"))


async def sim():
    async with websockets.connect(f"{BASE}/tel/sim/ws?phone=%2B919800000001") as ws:
        async def recv():
            return json.loads(await asyncio.wait_for(ws.recv(), 10))

        async def key(d, call_id, seq, ts=None):
            if ts is None:
                await asyncio.sleep(0.2)   # human pace; the same digit within 120 ms is dropped as bounce
            await ws.send(json.dumps({"t": "digit", "call_id": call_id, "d": d,
                                      "ts_ms": ts or int(time.time() * 1000), "seq": seq}))

        await ws.send(json.dumps({"t": "missed_call"}))
        ring = await recv()
        assert ring["t"] == "ring", ring
        cid = ring["call_id"]
        await ws.send(json.dumps({"t": "answer", "call_id": cid}))
        states = [(await recv())["state"]]                 # LANG
        seq = 0
        # LANG 1, CONSENT 1, CROP 1
        for d in "111":
            seq += 1
            await key(d, cid, seq)
            states.append((await recv())["state"])
        # QTY with bounce: 3 sent twice within 40 ms, then #
        await asyncio.sleep(0.2)
        t0 = int(time.time() * 1000)
        await key("3", cid, seq + 1, t0)
        await key("3", cid, seq + 2, t0 + 35)
        await asyncio.sleep(0.4)
        await key("#", cid, seq + 3, int(time.time() * 1000))
        seq += 3
        states.append((await recv())["state"])             # QTY_CONFIRM
        await key("1", cid, seq + 1)
        states.append((await recv())["state"])             # PRICE
        # PRICE 3200 then timeout ends entry
        for i, d in enumerate("3200"):
            await key(d, cid, seq + 2 + i)
        seq += 6
        await ws.send(json.dumps({"t": "timeout", "call_id": cid, "seq": seq}))
        states.append((await recv())["state"])             # GUARD
        for _ in range(2):                                 # GUARD 1, FINAL 1
            seq += 1
            await key("1", cid, seq)
            states.append((await recv())["state"])
        hang = await recv()
        assert hang["t"] == "hangup", hang
        print("sim ws OK:", " -> ".join(states), "-> hangup")


async def main():
    await asyncio.gather(dashboard(), sim())


asyncio.run(main())
