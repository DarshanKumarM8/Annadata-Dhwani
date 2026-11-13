"""Keypad bounce filter for per-digit paths (simulator). Owner: Darshan.

Drop the same digit repeated within SAME_MS, and any digit arriving within ANY_MS of the previous one.
Exotel's Gather returns a finished string with no timing, so this cannot run there (plan section 5.4).
"""
SAME_MS = 120
ANY_MS = 40


class Debouncer:
    def __init__(self) -> None:
        self.last: tuple[str, int] | None = None

    def is_bounce(self, digit: str, ts_ms: int) -> bool:
        """True if this press is a bounce. The press is remembered either way, so a bounce train stays dropped."""
        last, self.last = self.last, (digit, ts_ms)
        if last is None:
            return False
        gap = ts_ms - last[1]
        return gap < ANY_MS or (last[0] == digit and gap < SAME_MS)
