"""Settings from the environment (and the repo-root .env, if present). Owner: Darshan."""
import os
import re
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
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-32-random-chars")
    fail_ticket_threshold: int = 3
    call_cap_s: int = int(os.getenv("CALL_CAP_S", "240"))
    session_ttl_s: int = 1800
    audio_dir: Path = ROOT / "audio"
    media_dir: Path = ROOT / "media"
    auction_s: int = int(os.getenv("AUCTION_S", "180" if os.getenv("DEMO_MODE", "1") == "1" else "86400"))
    confirm_s: int = int(os.getenv("CONFIRM_S", "90" if os.getenv("DEMO_MODE", "1") == "1" else "7200"))
    sim_incoming_ring_s: float = float(os.getenv("SIM_INCOMING_RING_S", "30"))
    job_max_parallel: int = int(os.getenv("JOB_MAX_PARALLEL", "5"))
    job_backoff_s: tuple = (20, 40, 60) if os.getenv("DEMO_MODE", "1") == "1" else (120, 600, 1800)
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
    exotel_sid: str = os.getenv("EXOTEL_SID", "")
    exotel_api_key: str = os.getenv("EXOTEL_API_KEY", "")
    exotel_api_token: str = os.getenv("EXOTEL_API_TOKEN", "")
    exophone: str = os.getenv("EXOPHONE", "")
    exotel_app_id: str = os.getenv("EXOTEL_APP_ID", "")
    exotel_api_host: str = os.getenv("EXOTEL_API_HOST", "api.exotel.com")
    unknown_cb_ttl_s: int = int(os.getenv("UNKNOWN_CB_TTL_S", "60" if os.getenv("DEMO_MODE", "1") == "1" else "86400"))
    # real numbers the server may dial (last 10 digits of each TEAM_PHONES entry). Empty = no restriction.
    team_phones: frozenset = frozenset(re.sub(r"\D", "", p)[-10:] for p in re.split(r"[,;\s]+", os.getenv("TEAM_PHONES", "")) if p)
    # 0 = send exactly the Gather reply that worked on the first full call. 2 = ask Exotel to repeat the menu twice when nobody
    # presses a key (documented by Exotel, but not yet proven with our flow): try it with EXOTEL_REPEAT_MENU=2 and read the trace.
    exotel_repeat_menu: int = int(os.getenv("EXOTEL_REPEAT_MENU", "0"))
    verify_radius_m: int = int(os.getenv("VERIFY_RADIUS_M", "500"))


settings = Settings()
