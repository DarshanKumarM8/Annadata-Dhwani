"""Bridge to Hitesh's services/audio.py (contract C9) with a stand-in until H4 merges. Owner: Darshan.

Once services/audio.py exists, the real functions are used automatically. Until then:
  digit_clips works locally and mix_path returns the shared sample beep.
"""
import logging

log = logging.getLogger("audio_shim")

try:  # pragma: no cover - depends on whether H4 has merged
    from ..services import audio as _audio  # type: ignore
except Exception:  # ImportError or a half-written module
    _audio = None


def digit_clips(n: int) -> list[str]:
    if _audio and hasattr(_audio, "digit_clips"):
        return _audio.digit_clips(n)
    return [f"d_{c}" for c in str(int(n))]


def mix_url(clips: list[str], lang: str) -> str:
    """Server-relative URL of the mixed WAV for these clips (the client prefixes API_BASE)."""
    if _audio and hasattr(_audio, "mix"):
        try:
            return f"/audio/mix/{_audio.mix(clips, lang)}.wav"
        except Exception:
            log.exception("audio.mix failed, using sample beep")
    return "/audio/mix/sample.wav"
