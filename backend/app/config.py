"""Settings from the environment (and the repo-root .env, if present). Owner: Darshan."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/annadata")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    provider: str = os.getenv("TELEPHONY_PROVIDER", "sim")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    demo_mode: bool = os.getenv("DEMO_MODE", "1") == "1"
    # simulator timing (spec C6: ring after 1-3 s; hangup follows the last prompt)
    sim_ring_min: float = float(os.getenv("SIM_RING_MIN", "1"))
    sim_ring_max: float = float(os.getenv("SIM_RING_MAX", "3"))
    sim_hangup_delay: float = float(os.getenv("SIM_HANGUP_DELAY", "1.5"))
    cb_limit_10m: int = int(os.getenv("RL_CB_10M", "3"))      # callbacks per number per 10 min
    cb_limit_day: int = int(os.getenv("RL_CB_DAY", "6"))       # callbacks per number per day
    daily_call_budget: int = int(os.getenv("DAILY_CALL_BUDGET", "200"))
    fail_ticket_threshold: int = 3
    call_cap_s: int = int(os.getenv("CALL_CAP_S", "240"))
    session_ttl_s: int = 1800
    audio_dir: Path = ROOT / "audio"


settings = Settings()
