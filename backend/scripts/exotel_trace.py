"""Show the last Exotel webhook requests, newest first. Owner: Darshan.

  python backend/scripts/exotel_trace.py            # last 25
  python backend/scripts/exotel_trace.py 80

Every request Exotel makes to our server is recorded (path, step, masked numbers, answer code, how long we took, what the
server decided). The secret is never stored. Read it right after a test call: the order of the lines tells the story:
  missed -> (callback placed) -> gather step 1 -> digits step 1 -> gather step 2 -> ... -> status
If a call ends with no 'gather' line, Exotel never asked us for a prompt (check the flow in the Exotel dashboard).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis.asyncio as aioredis  # noqa: E402

from app.config import settings  # noqa: E402


async def main(n: int) -> None:
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    rows = [json.loads(x) for x in await r.lrange("exo:trace", 0, n - 1)]
    await r.aclose()
    if not rows:
        print("Nothing traced yet (the server must be running the latest code, and a call must have happened in the last day).")
        return
    print(f"{'time (UTC)':<10} {'call':<9} {'request':<8} {'step':<4} {'code':<4} {'ms':<5} {'from':<13} what")
    for x in reversed(rows):
        extra = " ".join(f"{k}={x[k]}" for k in ("status", "duration", "digits") if x.get(k))
        print(f"{x['t'][11:19]:<10} {x.get('sid', ''):<9} {x['path']:<8} {str(x.get('step', '')):<4} {x['code']:<4} {x.get('ms', 0):<5} "
              f"{x.get('from', ''):<13} {extra} {x.get('note', '')}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 25))
