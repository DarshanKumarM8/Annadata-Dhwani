"""Background sweeper: abandoned call sessions become EXPIRED. Runs every 5 minutes. Owner: Darshan."""
import asyncio
import logging

from ..engine import session as store

log = logging.getLogger("sweeper")


async def run(interval_s: int = 300) -> None:
    while True:
        try:
            n = await store.expire_stale()
            if n:
                log.info("expired %d stale call sessions", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sweeper pass failed")
        await asyncio.sleep(interval_s)
