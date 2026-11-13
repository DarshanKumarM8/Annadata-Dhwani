"""Engine <-> adapter vocabulary. Owner: Darshan."""
from dataclasses import dataclass, field


@dataclass
class Event:
    kind: str                      # "start" | "digits" | "timeout" | "hangup"
    digits: str = ""               # collected string for kind == "digits"
    call_id: str = ""
    phone: str = ""                # needed on "start"
    event_id: str = ""             # unique per provider event (idempotency, D3)
    ts_ms: int = 0
    job: dict | None = None        # outbound-call job on "start" (BID_OFFER): {id, kind, payload}
    job: dict | None = None        # outbound-call job on "start" (BID_OFFER): {"id","kind","payload"}


@dataclass
class Action:
    """What the adapter must do next: play clips, collect digits, or hang up."""
    clips: list[str] = field(default_factory=list)
    lang: str = "kn"
    max_digits: int = 0
    finish_on_key: str = ""
    timeout_s: int = 6
    state: str = ""
    hangup: bool = False           # hang up after the clips have played
    hangup_now: bool = False       # hang up immediately, nothing to play
