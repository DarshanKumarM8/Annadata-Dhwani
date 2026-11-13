"""FastAPI entry point. Run from backend/:  uvicorn app.main:app --port 8000. Owner: Darshan."""
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import cache, db
from .config import ROOT, settings
from .engine.deps import PgDeps
from .api import agent, auth, buyer, clusters, ops, ws
from .services import bidding, sweeper
from .telephony import sim

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

SAMPLE = ROOT / "contracts" / "fixtures" / "sample.wav"


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await db.connect()
    await cache.connect()
    app.state.deps = PgDeps(pool)
    sweep = asyncio.create_task(sweeper.run())
    hub = asyncio.create_task(ws.hub.run())
    auctions = asyncio.create_task(bidding.run())
    yield
    sweep.cancel()
    hub.cancel()
    auctions.cancel()
    await cache.close()
    await db.close()


app = FastAPI(title="Annadata Dhwani", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(sim.router)
app.include_router(ops.router)
app.include_router(auth.router)
app.include_router(clusters.router)
app.include_router(buyer.router)
app.include_router(agent.router)
app.include_router(ws.router)


@app.exception_handler(auth.ApiError)
async def api_error(_: Request, e: auth.ApiError):
    return JSONResponse(e.body, status_code=e.status)


@app.exception_handler(HTTPException)
async def http_error(_: Request, e: HTTPException):
    # contract error shape is {"error": CODE, ...}, not FastAPI's {"detail": ...}
    return JSONResponse(e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)},
                        status_code=e.status_code)


@app.get("/audio/mix/{name}")
async def audio_mix(name: str):
    """Mixed prompt WAVs. Falls back to the sample beep while services/audio.py (H4) is not merged."""
    f = settings.audio_dir / "mix" / name
    if f.is_file() and f.resolve().parent == (settings.audio_dir / "mix").resolve():
        return FileResponse(f, media_type="audio/wav")
    return FileResponse(SAMPLE, media_type="audio/wav")


@app.get("/demo", include_in_schema=False)
async def demo_board():
    """One-page live board for judges: clusters, bids, deals and the event feed. Stopgap until the real UIs merge."""
    return FileResponse(Path(__file__).parent / "static" / "demo.html", media_type="text/html")


@app.get("/media/v/{name}")
async def media(name: str):
    f = settings.media_dir / "v" / name
    if f.is_file() and f.resolve().parent == (settings.media_dir / "v").resolve():
        return FileResponse(f)
    return FileResponse(ROOT / "contracts" / "fixtures" / "sample.svg", media_type="image/svg+xml")


@app.get("/health")
async def health():
    out = {"db": "down", "redis": "down", "provider": settings.provider}
    mix = settings.audio_dir / "mix"
    out["tts_clips"] = len(list(mix.glob("*.wav"))) if mix.is_dir() else 0
    try:
        await db.pool.fetchval("SELECT 1")
        out["db"] = "ok"
        await cache.redis.ping()
        out["redis"] = "ok"
        age = await db.pool.fetchval("SELECT current_date - max(price_date) FROM mandi_prices")
        out["price_age_days"] = age
    except Exception:
        return JSONResponse(out, status_code=503)
    return out
