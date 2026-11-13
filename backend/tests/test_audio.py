"""
backend/tests/test_audio.py — pytest suite for audio.py (H4)

Tests:
  1. digit_clips — basic and edge cases
  2. mix duration = sum of clip durations + 150 ms * (n-1) gaps
  3. Cache hit — second mix() call returns same sha without rewriting the file (mtime unchanged)
  4. Lang-override prefix "<lang>:<clip>" picks the right language file
  5. Missing clip raises FileNotFoundError with the clip name
  6. Concurrency — 20 threads mixing the same list produce one valid file
  7. mix_url — correct URL format
  8. missing_clips — reports absent files correctly

No external libraries beyond pytest and Python stdlib.
WAV files are generated synthetically with math.sin to avoid needing real audio assets.
"""

from __future__ import annotations

import math
import os
import struct
import threading
import time
import wave
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Import audio.py — try package path first, then direct path
# ---------------------------------------------------------------------------
def _import_audio():
    try:
        from backend.app.services.audio import (
            AUDIO_ROOT, digit_clips, missing_clips, mix, mix_url, _compute_sha,
        )
        return AUDIO_ROOT, digit_clips, missing_clips, mix, mix_url, _compute_sha
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.services.audio import (  # type: ignore[import]
            AUDIO_ROOT, digit_clips, missing_clips, mix, mix_url, _compute_sha,
        )
        return AUDIO_ROOT, digit_clips, missing_clips, mix, mix_url, _compute_sha


AUDIO_ROOT, digit_clips, missing_clips, mix, mix_url, _compute_sha = _import_audio()


# ---------------------------------------------------------------------------
# Helpers — synthetic WAV generation
# ---------------------------------------------------------------------------
SAMPLE_RATE = 8000
SAMPWIDTH = 2
NCHANNELS = 1


def _make_wav(path: Path, duration_ms: int, freq: float = 440.0) -> None:
    """Write a pure sine-wave WAV at the given duration to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(SAMPLE_RATE * duration_ms / 1000)
    frames = bytearray()
    for i in range(n_frames):
        sample = int(32767 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(NCHANNELS)
        wf.setsampwidth(SAMPWIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(frames))


def _wav_duration_ms(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate() * 1000


def _patch_audio_root(tmp_path: Path, monkeypatch) -> Path:
    """Override AUDIO_ROOT and MIX_DIR in the audio module.

    Uses sys.modules to find the exact module object the top-level
    imports resolved to, regardless of import path variant.
    """
    import sys as _sys
    _audio = (
        _sys.modules.get("backend.app.services.audio")
        or _sys.modules.get("app.services.audio")
    )
    if _audio is None:
        try:
            import app.services.audio as _audio  # type: ignore[import]
        except ModuleNotFoundError:
            import importlib
            _audio = importlib.import_module("app.services.audio")
    monkeypatch.setattr(_audio, "AUDIO_ROOT", tmp_path)
    monkeypatch.setattr(_audio, "MIX_DIR", tmp_path / "mix")
    return tmp_path


# ---------------------------------------------------------------------------
# 1. digit_clips
# ---------------------------------------------------------------------------
class TestDigitClips:
    def test_zero(self):
        assert digit_clips(0) == ["d_0"]

    def test_single_digit(self):
        assert digit_clips(7) == ["d_7"]

    def test_multi_digit(self):
        assert digit_clips(3430) == ["d_3", "d_4", "d_3", "d_0"]

    def test_two_digit(self):
        assert digit_clips(42) == ["d_4", "d_2"]

    def test_leading_zero_as_string_input(self):
        # 100 -> d_1 d_0 d_0
        assert digit_clips(100) == ["d_1", "d_0", "d_0"]

    def test_listing_code(self):
        assert digit_clips(427) == ["d_4", "d_2", "d_7"]


# ---------------------------------------------------------------------------
# 2. mix duration = sum of clips + 280 ms * gaps
# ---------------------------------------------------------------------------
class TestMixDuration:
    def test_two_clips(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "clip_a.wav", 300)
        _make_wav(tmp_path / "kn" / "clip_b.wav", 500)

        sha = mix(["clip_a", "clip_b"], "kn")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - (300 + 500 + 280)) < 5  # one gap

    def test_three_clips(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        for name, dur in [("a", 200), ("b", 400), ("c", 300)]:
            _make_wav(tmp_path / "kn" / f"{name}.wav", dur)

        sha = mix(["a", "b", "c"], "kn")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - (200 + 400 + 300 + 280 * 2)) < 5  # two gaps

    def test_single_clip_no_gap(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "solo.wav", 400)
        sha = mix(["solo"], "kn")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - 400) < 5

    def test_different_languages_different_dirs(self, tmp_path, monkeypatch):
        """mix() uses audio/<lang>/clip.wav — lang is a pure runtime param."""
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "mr" / "clip.wav", 350)  # Marathi
        sha = mix(["clip"], "mr")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - 350) < 5


# ---------------------------------------------------------------------------
# 3. Cache hit — mtime unchanged on second call
# ---------------------------------------------------------------------------
class TestCacheHit:
    def test_same_sha_no_rewrite(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "x.wav", 200)

        sha1 = mix(["x"], "kn")
        out = tmp_path / "mix" / f"{sha1}.wav"
        mtime1 = out.stat().st_mtime

        time.sleep(0.05)
        sha2 = mix(["x"], "kn")

        assert sha1 == sha2
        assert out.stat().st_mtime == mtime1, "File was rewritten on cache hit"

    def test_different_clips_different_sha(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "p.wav", 100)
        _make_wav(tmp_path / "kn" / "q.wav", 100)
        assert mix(["p"], "kn") != mix(["q"], "kn")

    def test_different_lang_different_sha(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "clip.wav", 100)
        _make_wav(tmp_path / "hi" / "clip.wav", 100)
        assert mix(["clip"], "kn") != mix(["clip"], "hi")


# ---------------------------------------------------------------------------
# 4. Language override prefix "<lang>:<clip>"
# ---------------------------------------------------------------------------
class TestLangOverridePrefix:
    def test_override_picks_correct_file(self, tmp_path, monkeypatch):
        """
        'kn:lang_option' should pick audio/kn/lang_option.wav even inside a 'hi' mix.
        Duration difference proves which file was read.
        """
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "hi" / "lang_option.wav", 300)  # hi version = 300 ms
        _make_wav(tmp_path / "kn" / "lang_option.wav", 600)  # kn version = 600 ms
        _make_wav(tmp_path / "hi" / "welcome.wav", 200)

        # Play welcome in hi, but lang_option forced to kn
        sha = mix(["welcome", "kn:lang_option"], "hi")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - (200 + 600 + 280)) < 5

    def test_override_en_prefix_accepted(self, tmp_path, monkeypatch):
        """'en:lang_option' override must pick audio/en/lang_option.wav."""
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "en" / "lang_option.wav", 450)
        _make_wav(tmp_path / "kn" / "welcome.wav", 200)

        sha = mix(["welcome", "en:lang_option"], "kn")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - (200 + 450 + 280)) < 5

    def test_override_different_from_default(self, tmp_path, monkeypatch):
        """The override SHA must differ from the non-override SHA."""
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "clip.wav", 300)
        _make_wav(tmp_path / "hi" / "clip.wav", 600)

        sha_kn = mix(["clip"], "kn")
        sha_kn_via_override = mix(["kn:clip"], "hi")
        # kn:clip inside hi mix has different prefix sequence → different sha
        assert sha_kn != sha_kn_via_override

    def test_any_lang_code_accepted(self, tmp_path, monkeypatch):
        """The module must not validate or restrict language codes."""
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "mr" / "welcome.wav", 250)  # Marathi
        sha = mix(["mr:welcome"], "kn")
        actual = _wav_duration_ms(tmp_path / "mix" / f"{sha}.wav")
        assert abs(actual - 250) < 5


# ---------------------------------------------------------------------------
# 5. Missing clip raises FileNotFoundError
# ---------------------------------------------------------------------------
class TestMissingClip:
    def test_missing_raises(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        with pytest.raises(FileNotFoundError, match="ghost_clip"):
            mix(["ghost_clip"], "kn")

    def test_missing_clips_function(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "present.wav", 100)

        result = missing_clips(["present", "absent"], ["kn", "hi"])
        assert "hi/present" in result   # hi/present not on disk
        assert "kn/absent" in result
        assert "hi/absent" in result
        assert "kn/present" not in result  # kn/present exists

    def test_missing_clips_with_override(self, tmp_path, monkeypatch):
        """'mr:clip' should check audio/mr/clip.wav only."""
        _patch_audio_root(tmp_path, monkeypatch)
        result = missing_clips(["mr:welcome"], ["kn", "hi"])
        # Only mr/welcome should be reported, not kn/welcome or hi/welcome
        assert "mr/welcome" in result
        assert "kn/welcome" not in result
        assert "hi/welcome" not in result

    def test_missing_clips_any_lang(self, tmp_path, monkeypatch):
        """missing_clips must accept any lang code, not a hardcoded list."""
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "te" / "clip.wav", 100)  # Telugu
        result = missing_clips(["clip"], ["te", "ta"])
        assert "te/clip" not in result  # exists
        assert "ta/clip" in result     # missing


# ---------------------------------------------------------------------------
# 6. Concurrency — 20 threads, same clip list → one valid file
# ---------------------------------------------------------------------------
class TestConcurrency:
    def test_20_threads_one_file(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "t1.wav", 200)
        _make_wav(tmp_path / "kn" / "t2.wav", 300)

        shas: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def _worker():
            try:
                s = mix(["t1", "t2"], "kn")
                with lock:
                    shas.append(s)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent errors: {errors}"
        assert len(shas) == 20
        assert len(set(shas)) == 1, "Threads produced different shas"

        sha = shas[0]
        out = tmp_path / "mix" / f"{sha}.wav"
        assert out.exists()
        assert abs(_wav_duration_ms(out) - (200 + 300 + 280)) < 5


# ---------------------------------------------------------------------------
# 7. mix_url
# ---------------------------------------------------------------------------
class TestMixUrl:
    def test_url_format(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "u.wav", 100)

        url = mix_url(["u"], "kn", "http://localhost:8000")
        sha = _compute_sha("kn", ["u"])
        assert url == f"http://localhost:8000/audio/mix/{sha}.wav"

    def test_no_double_slash(self, tmp_path, monkeypatch):
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "kn" / "v.wav", 100)
        url = mix_url(["v"], "kn", "https://example.ngrok.io")
        assert "//audio" not in url

    def test_works_for_any_lang(self, tmp_path, monkeypatch):
        """mix_url must not hardcode any language."""
        _patch_audio_root(tmp_path, monkeypatch)
        _make_wav(tmp_path / "mr" / "clip.wav", 100)
        url = mix_url(["clip"], "mr", "http://localhost:8000")
        assert "/audio/mix/" in url
        assert url.endswith(".wav")
