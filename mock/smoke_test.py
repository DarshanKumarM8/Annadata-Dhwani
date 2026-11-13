"""Smoke test for the mock server's two WebSockets (C5, C6). Run while mock_server.py is up:
    python mock/smoke_test.py
Needs: pip install websockets"""
import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.audio import mix as mix_audio

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
        lang_prompt = await recv()
        states = [lang_prompt["state"]]
        seq = 0
        # LANG 3 (English), CONSENT 1, CROP 1
        lang_url = f"/audio/mix/{mix_audio(['welcome', 'kn:lang_option', 'hi:lang_option', 'en:lang_option'], 'kn')}.wav"
        assert lang_prompt["audio_url"] == lang_url
        for d in "311":
            seq += 1
            await key(d, cid, seq)
            states.append((await recv())["state"])
        # QTY with bounce and exact readback: 1 is bounced, then 7 makes 17.
        await asyncio.sleep(0.2)
        t0 = int(time.time() * 1000)
        await key("1", cid, seq + 1, t0)
        await key("1", cid, seq + 2, t0 + 35)
        await asyncio.sleep(0.4)
        await key("7", cid, seq + 3, int(time.time() * 1000))
        await key("#", cid, seq + 4)
        seq += 4
        qty_prompt = await recv()
        states.append(qty_prompt["state"])                 # QTY_CONFIRM
        expected_17 = mix_audio(["you_entered", "qty_17", "confirm_1_2"], "en")
        assert qty_prompt["audio_url"] == f"/audio/mix/{expected_17}.wav"
        seq += 1
        await key("2", cid, seq)                          # re-enter quantity
        states.append((await recv())["state"])             # QTY
        seq += 1
        await key("4", cid, seq)
        seq += 1
        await key("2", cid, seq)
        qty_prompt = await recv()
        states.append(qty_prompt["state"])                 # QTY_CONFIRM
        expected_42 = mix_audio(["you_entered", "qty_42", "confirm_1_2"], "en")
        assert qty_prompt["audio_url"] == f"/audio/mix/{expected_42}.wav"
        seq += 1
        await key("1", cid, seq)
        states.append((await recv())["state"])             # PRICE
        # PRICE 3200 then timeout ends entry
        for d in "3200":
            seq += 1
            await key(d, cid, seq)
        seq += 1
        await ws.send(json.dumps({"t": "timeout", "call_id": cid, "seq": seq}))
        states.append((await recv())["state"])             # GUARD
        seq += 1
        await key("1", cid, seq)                          # GUARD 1 re-enters PRICE
        states.append((await recv())["state"])
        for d in "3500":
            seq += 1
            await key(d, cid, seq)
        seq += 1
        await ws.send(json.dumps({"t": "timeout", "call_id": cid, "seq": seq}))
        final_prompt = await recv()
        states.append(final_prompt["state"])
        expected_final = mix_audio(
            ["final_intro", "qty_42", "crop_ragi", "at_price", "d_3", "d_5", "d_0", "d_0",
             "rupees_per_qtl", "final_confirm"],
            "en",
        )
        assert final_prompt["audio_url"] == f"/audio/mix/{expected_final}.wav", (
            final_prompt["audio_url"], f"/audio/mix/{expected_final}.wav"
        )
        seq += 1
        await key("1", cid, seq)
        states.append((await recv())["state"])
        hang = await recv()
        assert hang["t"] == "hangup", hang
        print("sim ws OK:", " -> ".join(states), "-> hangup")


async def hindi():
    async with websockets.connect(f"{BASE}/tel/sim/ws?phone=%2B919800000002") as ws:
        async def recv():
            return json.loads(await asyncio.wait_for(ws.recv(), 10))

        await ws.send(json.dumps({"t": "missed_call"}))
        ring = await recv()
        await ws.send(json.dumps({"t": "answer", "call_id": ring["call_id"]}))
        language_prompt = await recv()
        assert language_prompt["state"] == "LANG"
        await ws.send(json.dumps({"t": "digit", "call_id": ring["call_id"], "d": "2",
                                  "ts_ms": int(time.time() * 1000), "seq": 1}))
        consent = await recv()
        expected = mix_audio(["consent"], "hi")
        assert consent["state"] == "CONSENT"
        assert consent["audio_url"] == f"/audio/mix/{expected}.wav"
        print("Hindi language routing OK")


async def main():
    await asyncio.gather(dashboard(), sim(), hindi())


asyncio.run(main())
