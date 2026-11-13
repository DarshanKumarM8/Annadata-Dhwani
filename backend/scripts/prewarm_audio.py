#!/usr/bin/env python3
"""
prewarm_audio.py — Annadata Dhwani audio pre-generation pipeline (H3)

Reads backend/prompts.yaml and synthesises every clip with edge-tts,
then converts to 8 kHz mono 16-bit PCM WAV via FFmpeg.

No language or voice is hardcoded here.  Pass them on the command line.

Usage:
    # Generate Kannada clips (voice supplied by you):
    python prewarm_audio.py \\
        --langs kn \\
        --voices kn:kn-IN-SapnaNeural

    # Generate Kannada + Hindi:
    python prewarm_audio.py \\
        --langs kn,hi \\
        --voices kn:kn-IN-SapnaNeural,hi:hi-IN-SwaraNeural

    # Regenerate one clip for one language:
    python prewarm_audio.py --langs kn --voices kn:kn-IN-SapnaNeural \\
        --only ask_qty

    # Verify files already on disk (pass the langs you want to check):
    python prewarm_audio.py --langs kn,hi --check

    # List all available edge-tts voices:
    python prewarm_audio.py --list-voices

Language codes match whatever the farmer's DB `lang` field can hold
(e.g. kn, hi, mr, te, ta …).  The script does not know or care which
languages exist; you decide at the command line.

For each clip the script looks up entry[lang] in prompts.yaml.
If that field is absent or empty it prints a warning and skips the clip.
Native speakers should add the translations directly to prompts.yaml.

Output: audio/<lang>/<clip_id>.wav  +  audio/<lang>/<clip_id>.sha
FFmpeg filter: highpass=f=300,lowpass=f=3400,loudnorm=I=-16:TP=-3:LRA=7
SHA scheme:    sha256("lang|voice|text")  — detects if text or voice changed
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import yaml  # pip install pyyaml

# ---------------------------------------------------------------------------
# Paths  (no language-specific constants here)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
PROMPTS_YAML = REPO_ROOT / "backend" / "prompts.yaml"
AUDIO_ROOT = REPO_ROOT / "audio"

EDGE_RATE = "-5%"


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
def parse_voices(raw: str) -> dict[str, str]:
    """
    Parse "kn:kn-IN-SapnaNeural,hi:hi-IN-SwaraNeural" into a dict.
    Raises ValueError on bad format.
    """
    result: dict[str, str] = {}
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" not in token:
            raise ValueError(
                f"Bad --voices entry '{token}'. "
                "Expected format: lang:VoiceName  e.g.  kn:kn-IN-SapnaNeural"
            )
        lang, voice = token.split(":", 1)
        result[lang.strip()] = voice.strip()
    return result


def parse_langs(raw: str) -> list[str]:
    return [l.strip() for l in raw.split(",") if l.strip()]


# ---------------------------------------------------------------------------
# SHA computation
# ---------------------------------------------------------------------------
def compute_sha(lang: str, voice: str, text: str) -> str:
    """sha256 of 'lang|voice|text', full hex digest (stored in .sha file)."""
    blob = f"{lang}|{voice}|{text}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def sha_path(lang: str, clip_id: str) -> Path:
    return AUDIO_ROOT / lang / f"{clip_id}.sha"


def wav_path(lang: str, clip_id: str) -> Path:
    return AUDIO_ROOT / lang / f"{clip_id}.wav"


def read_stored_sha(lang: str, clip_id: str) -> str | None:
    p = sha_path(lang, clip_id)
    if p.exists():
        return p.read_text().strip()
    return None


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------
def atomic_write_bytes(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(dest: Path, text: str) -> None:
    atomic_write_bytes(dest, text.encode("utf-8"))


# ---------------------------------------------------------------------------
# FFmpeg conversion
# ---------------------------------------------------------------------------
def ffmpeg_convert(mp3_path: Path, wav_out: Path) -> None:
    """Convert TTS mp3/audio to 8 kHz mono 16-bit PCM WAV with IVR-grade filters."""
    wav_tmp = wav_out.parent / (wav_out.stem + ".converting.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(mp3_path),
        "-af", "highpass=f=300,lowpass=f=3400,loudnorm=I=-16:TP=-3:LRA=7",
        "-ar", "8000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(wav_tmp),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    os.replace(wav_tmp, wav_out)


# ---------------------------------------------------------------------------
# edge-tts synthesis
# ---------------------------------------------------------------------------
async def synthesise_edge(text: str, voice: str, mp3_out: Path) -> None:
    """Synthesise text using edge-tts with the given voice and save to mp3_out."""
    try:
        import edge_tts  # pip install edge-tts
    except ImportError:
        print("ERROR: edge-tts not installed.  pip install edge-tts", file=sys.stderr)
        raise

    communicate = edge_tts.Communicate(text, voice, rate=EDGE_RATE)
    mp3_out.parent.mkdir(parents=True, exist_ok=True)
    await communicate.save(str(mp3_out))


# ---------------------------------------------------------------------------
# Single-clip generation
# ---------------------------------------------------------------------------
async def generate_clip(
    clip_id: str,
    lang: str,
    voice: str,
    text: str,
    *,
    force: bool = False,
) -> str:
    """
    Synthesise audio/<lang>/<clip_id>.wav and write its .sha file.

    Returns one of: "skipped", "generated", "failed".
    Skips (without error) if the .wav already exists and the .sha matches.
    """
    expected_sha = compute_sha(lang, voice, text)
    w_path = wav_path(lang, clip_id)

    if not force and w_path.exists() and read_stored_sha(lang, clip_id) == expected_sha:
        return "skipped"

    mp3_tmp = AUDIO_ROOT / lang / f"{clip_id}.tmp.mp3"
    try:
        await synthesise_edge(text, voice, mp3_tmp)
        ffmpeg_convert(mp3_tmp, w_path)
        atomic_write_text(sha_path(lang, clip_id), expected_sha)
        return "generated"
    except Exception as exc:
        print(f"  [FAIL] {lang}/{clip_id}: {exc}", file=sys.stderr)
        return "failed"
    finally:
        # Windows: the mp3 may still be held briefly by the FFmpeg subprocess.
        # Swallow PermissionError — the file will be cleaned up on the next run.
        try:
            if mp3_tmp.exists():
                mp3_tmp.unlink(missing_ok=True)
        except PermissionError:
            pass


# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------
def check_all(clips: dict, langs: list[str]) -> None:
    """Verify every WAV file for the requested languages: 8000 Hz, 1 ch, sampwidth 2."""
    missing: list[str] = []
    bad: list[str] = []
    ok = 0

    for clip_id in clips:
        for lang in langs:
            w = wav_path(lang, clip_id)
            if not w.exists():
                missing.append(f"{lang}/{clip_id}")
                continue
            try:
                with wave.open(str(w), "rb") as wf:
                    if (
                        wf.getframerate() != 8000
                        or wf.getnchannels() != 1
                        or wf.getsampwidth() != 2
                    ):
                        bad.append(
                            f"{lang}/{clip_id} "
                            f"(rate={wf.getframerate()} "
                            f"ch={wf.getnchannels()} "
                            f"sw={wf.getsampwidth()})"
                        )
                    else:
                        ok += 1
            except Exception as e:
                bad.append(f"{lang}/{clip_id} ({e})")

    print("\n=== Check results ===")
    print(f"  OK      : {ok}")
    print(f"  Missing : {len(missing)}")
    print(f"  Bad     : {len(bad)}")

    if missing:
        print("\nMissing clips:")
        for m in missing:
            print(f"  - {m}")
    if bad:
        print("\nBad files (wrong format):")
        for b in bad:
            print(f"  - {b}")

    if missing or bad:
        sys.exit(1)
    else:
        print("\nAll files OK: 8000 Hz / mono / 16-bit PCM")


# ---------------------------------------------------------------------------
# --list-voices helper
# ---------------------------------------------------------------------------
async def list_voices() -> None:
    """Print all available edge-tts voices."""
    try:
        import edge_tts
    except ImportError:
        print("ERROR: edge-tts not installed.  pip install edge-tts", file=sys.stderr)
        sys.exit(1)

    voices = await edge_tts.list_voices()
    for v in sorted(voices, key=lambda x: x["Locale"]):
        print(f"  {v['Locale']:<12} {v['ShortName']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Annadata Dhwani audio pre-warmer (edge-tts). "
                    "No language or voice is hardcoded — pass them as arguments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python prewarm_audio.py --langs kn --voices kn:kn-IN-SapnaNeural
  python prewarm_audio.py --langs kn,hi --voices kn:kn-IN-SapnaNeural,hi:hi-IN-SwaraNeural
  python prewarm_audio.py --langs kn --voices kn:kn-IN-SapnaNeural --only ask_qty
  python prewarm_audio.py --langs kn,hi --check
  python prewarm_audio.py --list-voices
        """,
    )

    parser.add_argument(
        "--langs",
        metavar="LANG[,LANG...]",
        help=(
            "Comma-separated language codes to generate, e.g. kn,hi,mr. "
            "Must correspond to fields in prompts.yaml and entries in --voices."
        ),
    )
    parser.add_argument(
        "--voices",
        metavar="LANG:VOICE[,LANG:VOICE...]",
        help=(
            "edge-tts voice to use for each language, e.g. "
            "kn:kn-IN-SapnaNeural,hi:hi-IN-SwaraNeural. "
            "Run --list-voices to see all available voices."
        ),
    )
    parser.add_argument(
        "--only",
        metavar="CLIP_ID",
        help="Regenerate one specific clip id only (forces regeneration).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify all WAV files for --langs and exit (no synthesis).",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print all available edge-tts voices and exit.",
    )
    parser.add_argument(
        "--text-fallback",
        metavar="LANG",
        default=None,
        help=(
            "If a clip has no text for the requested language, fall back to "
            "this language's text instead of skipping.  "
            "Example: --text-fallback en  (use English text to generate kn/hi "
            "placeholder clips until a native speaker fills prompts.yaml)"
        ),
    )
    args = parser.parse_args()

    # --list-voices: no other args needed
    if args.list_voices:
        await list_voices()
        return

    # All other modes require --langs
    if not args.langs:
        parser.error(
            "--langs is required. "
            "Example: --langs kn,hi"
        )

    langs = parse_langs(args.langs)

    # --check does not need --voices
    if args.check:
        if not PROMPTS_YAML.exists():
            print(f"ERROR: prompts.yaml not found at {PROMPTS_YAML}", file=sys.stderr)
            sys.exit(1)
        with PROMPTS_YAML.open("r", encoding="utf-8") as f:
            clips: dict = yaml.safe_load(f)
        check_all(clips, langs)
        return

    # Generation mode: --voices is required
    if not args.voices:
        parser.error(
            "--voices is required for generation. "
            "Example: --voices kn:kn-IN-SapnaNeural,hi:hi-IN-SwaraNeural\n"
            "Run --list-voices to see all available edge-tts voices."
        )

    voice_map = parse_voices(args.voices)

    # Validate every requested lang has a voice
    missing_voices = [l for l in langs if l not in voice_map]
    if missing_voices:
        parser.error(
            f"No voice provided for language(s): {', '.join(missing_voices)}. "
            f"Add them to --voices, e.g. --voices {missing_voices[0]}:<VoiceName>"
        )

    # Load prompts
    if not PROMPTS_YAML.exists():
        print(f"ERROR: prompts.yaml not found at {PROMPTS_YAML}", file=sys.stderr)
        sys.exit(1)

    with PROMPTS_YAML.open("r", encoding="utf-8") as f:
        clips = yaml.safe_load(f)

    # Determine target clips
    if args.only:
        if args.only not in clips:
            print(f"ERROR: clip_id '{args.only}' not found in prompts.yaml", file=sys.stderr)
            sys.exit(1)
        target_clips = {args.only: clips[args.only]}
        force = True
    else:
        target_clips = clips
        force = False

    # Ensure output directories exist
    for lang in langs:
        (AUDIO_ROOT / lang).mkdir(parents=True, exist_ok=True)

    # Counters per language
    counters: dict[str, dict[str, int]] = {
        lang: {"generated": 0, "skipped": 0, "failed": 0, "no_text": 0}
        for lang in langs
    }

    total = len(target_clips) * len(langs)
    done = 0

    for clip_id, entry in target_clips.items():
        for lang in langs:
            done += 1
            voice = voice_map[lang]

            # Look up the translation for this language
            text = entry.get(lang) or ""
            if not text and args.text_fallback:
                fallback_text = entry.get(args.text_fallback) or ""
                if fallback_text:
                    print(
                        f"  [{done}/{total}] ⚠  {lang}/{clip_id}  "
                        f"(no '{lang}' text — using '{args.text_fallback}' fallback)"
                    )
                    text = fallback_text
            if not text:
                print(
                    f"  [{done}/{total}] ⚠  {lang}/{clip_id}  "
                    f"(no '{lang}' translation in prompts.yaml — skipped; "
                    f"add it in prompts.yaml after a native speaker provides it)"
                )
                counters[lang]["no_text"] += 1
                continue

            status = await generate_clip(clip_id, lang, voice, text, force=force)
            counters[lang][status] += 1
            symbol = {"generated": "✓", "skipped": "–", "failed": "✗"}.get(status, "?")
            print(f"  [{done}/{total}] {symbol} {lang}/{clip_id}  ({status})")

    # Summary
    print("\n=== Summary ===")
    for lang in langs:
        c = counters[lang]
        voice = voice_map[lang]
        print(
            f"  [{lang}] voice={voice}  "
            f"generated={c['generated']}  skipped={c['skipped']}  "
            f"failed={c['failed']}  no_translation={c['no_text']}"
        )

    total_failed = sum(c["failed"] for c in counters.values())
    total_no_text = sum(c["no_text"] for c in counters.values())

    if total_no_text:
        print(
            f"\n  ⚠  {total_no_text} clip(s) had no translation for the requested language(s).\n"
            f"     A native speaker should add those lines to backend/prompts.yaml."
        )
    if total_failed:
        print(f"\n  ✗  {total_failed} clip(s) failed — check logs above.")
        sys.exit(1)
    else:
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
