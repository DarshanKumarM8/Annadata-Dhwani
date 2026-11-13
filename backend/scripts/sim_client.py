"""Scripted caller that walks a full listing against a running backend. Owner: Darshan.

  python scripts/sim_client.py                       # ragi, 17 qtl, price 3600
  python scripts/sim_client.py --price 3000          # below the floor: exercises GUARD (needs a floor, see dev_min_seed.py)
  python scripts/sim_client.py --drop-after QTY_CONFIRM   # hang up mid-call; run again to see "welcome back"
  python scripts/sim_client.py --bounce              # send every key twice 30-60 ms apart
Needs the farmer to exist (python scripts/dev_min_seed.py). Prints each state and the prompt clip ids' URL.
"""
import argparse
import asyncio
import json
import random
import time
from urllib.parse import quote

import websockets


async def main(a) -> int:
    url = f"{a.base}/tel/sim/ws?phone={quote(a.phone)}"
    seq = 0
    states: list[str] = []
    async with websockets.connect(url) as ws:
        async def recv():
            return json.loads(await asyncio.wait_for(ws.recv(), 15))

        async def key(call_id, d):
            nonlocal seq
            await asyncio.sleep(0.2)                       # human pace; faster repeats are dropped as bounce
            ts = int(time.time() * 1000)
            seq += 1
            await ws.send(json.dumps({"t": "digit", "call_id": call_id, "d": d, "ts_ms": ts, "seq": seq}))
            if a.bounce:
                seq += 1
                await ws.send(json.dumps({"t": "digit", "call_id": call_id, "d": d,
                                          "ts_ms": ts + random.randint(30, 60), "seq": seq}))

        async def send_number(call_id, n: str, terminator="#"):
            for ch in n:
                await key(call_id, ch)
            await key(call_id, terminator)

        await ws.send(json.dumps({"t": "missed_call"}))
        ring = await recv()
        assert ring["t"] == "ring", ring
        cid = ring["call_id"]
        await ws.send(json.dumps({"t": "answer", "call_id": cid}))
        msg = await recv()
        while True:
            if msg["t"] == "hangup":
                break
            st = msg["state"]
            states.append(st)
            if len(states) > 40:
                print("giving up after 40 prompts (already listed this crop? try --crop 2 or run dev_min_seed.py --reset)")
                return 2
            print(f"{st:12} max={msg['max_digits']} fin={msg['finish_on_key']!r} {msg['audio_url']}")
            if st == a.drop_after:
                await ws.send(json.dumps({"t": "hangup", "call_id": cid}))
                print("dropped the call at", st)
                return 0
            if st in ("DONE", "HELP", "BYE", "NOT_REGISTERED"):
                msg = await recv()
                continue
            if st == "QTY":
                await send_number(cid, str(a.qty))
            elif st == "PRICE":
                await send_number(cid, str(a.price))
            elif st == "GUARD":
                await key(cid, a.guard)
            elif st == "CROP":
                await key(cid, a.crop)
            else:
                await key(cid, "1")                        # LANG(kn), CONSENT, MAIN, QTY_CONFIRM, FINAL
            msg = await recv()
    print("path:", " -> ".join(states))
    return 0 if states and states[-1] in ("DONE", "HELP", "BYE", "NOT_REGISTERED") else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="ws://localhost:8000")
    ap.add_argument("--phone", default="+919800000001")
    ap.add_argument("--crop", default="1")
    ap.add_argument("--qty", type=int, default=17)
    ap.add_argument("--price", type=int, default=3600)
    ap.add_argument("--guard", default="1", help="key at GUARD: 1 raise, 2 keep, 3 re-enter")
    ap.add_argument("--drop-after")
    ap.add_argument("--bounce", action="store_true")
    raise SystemExit(asyncio.run(main(ap.parse_args())))
