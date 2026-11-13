"""
backend/app/services/audio.py — Annadata Dhwani audio mixer (H4)

Contract C9 interface:
    digit_clips(n: int) -> list[str]
    mix(clips: list[str], lang: str) -> str          # returns sha, writes if absent
    mix_url(clips: list[str], lang: str, base_url: str) -> str
    missing_clips(clip_ids: list[str], langs: list[str]) -> list[str]

Clip files live at AUDIO_ROOT/<lang>/<clip_id>.wav (8000 Hz, mono, 16-bit PCM).
Mixed files are written atomically to AUDIO_ROOT/mix/<sha>.wav.

Language is a pure runtime parameter — it comes from the farmer's DB `lang` field,
which is set during the LANG IVR state and passed through by the telephony adapter
(Exotel / simulator).  This module has no hardcoded language list.

Clip-id override syntax:
    "<lang>:<clip_id>"  forces a specific language for one clip regardless of the
    caller's `lang`.  Example: ["welcome", "kn:lang_option", "ask_qty"].
    This is used by the LANG state to play each language's own menu option clip.
    Any valid language code can appear before the colon.

sha = sha256("|".join([lang] + clips)).hexdigest()[:24]
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Root directory — overrideable via env var (used by tests)
# ---------------------------------------------------------------------------
_ENV_AUDIO_ROOT = os.environ.get("AUDIO_ROOT", "")
if _ENV_AUDIO_ROOT:
    AUDIO_ROOT = Path(_ENV_AUDIO_ROOT).resolve()
else:
    # Repo layout: backend/app/services/audio.py -> repo root is 3 levels up
    AUDIO_ROOT = Path(__file__).resolve().parents[3] / "audio"

MIX_DIR = AUDIO_ROOT / "mix"

# 150 ms of silence at 8000 Hz, 16-bit mono
_SILENCE_FRAMES = int(0.150 * 8000)
_SILENCE_BYTES = b"\x00" * (_SILENCE_FRAMES * 2)  # sampwidth=2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def digit_clips(n: int) -> list[str]:
    """
    Convert an integer to a list of digit clip ids.

    Examples:
        digit_clips(3430) -> ["d_3", "d_4", "d_3", "d_0"]
        digit_clips(0)    -> ["d_0"]
        digit_clips(42)   -> ["d_4", "d_2"]
    """
    return [f"d_{ch}" for ch in str(n)]


def mix(clips: list[str], lang: str) -> str:
    """
    Concatenate WAV clips with 150 ms silence gaps and write to AUDIO_ROOT/mix/<sha>.wav.

    Returns the sha (first 24 hex chars of sha256("lang|clip1|clip2|...")).
    Returns immediately on cache hit (file already exists).

    Clip-id override: a clip id of the form "<other_lang>:<clip_name>" uses the
    WAV from audio/<other_lang>/<clip_name>.wav instead of audio/<lang>/<clip_name>.wav.
    Any language code is accepted before the colon — this module does not validate
    or restrict which languages exist.

    Raises FileNotFoundError naming the missing clip if a WAV is absent.
    Thread-safe: writes to a temp file then os.replace.
    """
    sha = _compute_sha(lang, clips)
    out_path = MIX_DIR / f"{sha}.wav"

    if out_path.exists():
        return sha  # cache hit — do not re-read clips

    MIX_DIR.mkdir(parents=True, exist_ok=True)

    all_frames: list[bytes] = []
    params = None

    for idx, clip_id in enumerate(clips):
        clip_lang, clip_name = _resolve_clip(clip_id, lang)
        clip_path = AUDIO_ROOT / clip_lang / f"{clip_name}.wav"

        if not clip_path.exists():
            raise FileNotFoundError(
                f"Audio clip not found: {clip_lang}/{clip_name}.wav "
                f"(full path: {clip_path})"
            )

        with wave.open(str(clip_path), "rb") as wf:
            if params is None:
                params = wf.getparams()
            frames = wf.readframes(wf.getnframes())

        all_frames.append(frames)

        # 150 ms silence between clips, not after the last one
        if idx < len(clips) - 1:
            all_frames.append(_SILENCE_BYTES)

    if params is None:
        # Empty clip list — produce a minimal valid silent WAV
        params = _silent_params()

    # Atomic write: temp file → os.replace
    # On Windows, os.replace can raise PermissionError if another thread already
    # won the race and the out_path is briefly locked.  If out_path exists after
    # the error the concurrent winner already wrote a valid file — accept that.
    fd, tmp_path = tempfile.mkstemp(dir=MIX_DIR, suffix=".tmp.wav")
    try:
        with os.fdopen(fd, "wb") as raw_fd:
            with wave.open(raw_fd, "wb") as wf_out:
                wf_out.setnchannels(params.nchannels)
                wf_out.setsampwidth(params.sampwidth)
                wf_out.setframerate(params.framerate)
                for chunk in all_frames:
                    wf_out.writeframes(chunk)
        try:
            os.replace(tmp_path, out_path)
        except PermissionError:
            # Windows: another thread just wrote the same file — that's fine.
            if not out_path.exists():
                raise  # genuinely broken, re-raise
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return sha


def mix_url(clips: list[str], lang: str, base_url: str) -> str:
    """
    Return the full URL to the mixed WAV, creating it if absent.

    base_url should have no trailing slash.
    Example: mix_url(["welcome"], "kn", "http://localhost:8000")
             -> "http://localhost:8000/audio/mix/<sha>.wav"
    """
    sha = mix(clips, lang)
    return f"{base_url}/audio/mix/{sha}.wav"


def missing_clips(clip_ids: list[str], langs: list[str]) -> list[str]:
    """
    Return "<lang>/<clip_id>" entries for every WAV that does not exist on disk.

    Respects the "<lang>:<clip_id>" override syntax: "kn:lang_option" checks
    audio/kn/lang_option.wav only, regardless of the `langs` argument.

    `langs` is whatever the caller passes — this function does not hardcode any
    language list.
    """
    missing: list[str] = []
    for clip_id in clip_ids:
        if ":" in clip_id:
            # Override: check only the specified language
            forced_lang, name = clip_id.split(":", 1)
            check_langs = [forced_lang]
        else:
            check_langs = langs
            name = clip_id

        for lang in check_langs:
            p = AUDIO_ROOT / lang / f"{name}.wav"
            if not p.exists():
                missing.append(f"{lang}/{name}")

    return missing


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_clip(clip_id: str, default_lang: str) -> tuple[str, str]:
    """
    Parse a clip id that may carry a language override.

    "<lang>:<name>" -> (lang, name)
    "<name>"        -> (default_lang, name)

    Only the first colon is treated as a separator, so clip names with colons
    are not supported (they don't exist in the C8 clip list).
    """
    if ":" in clip_id:
        lang, name = clip_id.split(":", 1)
        return lang, name
    return default_lang, clip_id


def _compute_sha(lang: str, clips: list[str]) -> str:
    key = "|".join([lang] + clips)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _silent_params():
    """Return wave params for a 1-frame silent WAV (edge case: empty clip list)."""
    import struct as _struct

    class _Params:
        nchannels = 1
        sampwidth = 2
        framerate = 8000
        nframes = 0
        comptype = "NONE"
        compname = "not compressed"

    return _Params()
