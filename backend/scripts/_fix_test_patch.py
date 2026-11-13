"""One-shot script: fix _patch_audio_root in test_audio.py to use sys.modules."""
import pathlib, re, sys

test_path = pathlib.Path(__file__).parent.parent / "tests" / "test_audio.py"
content = test_path.read_text(encoding="utf-8")

OLD = (
    "def _patch_audio_root(tmp_path: Path, monkeypatch) -> Path:\n"
    '    """Override AUDIO_ROOT and MIX_DIR in audio.py to point at tmp_path."""\n'
    "    import app.services.audio as _audio  # type: ignore[import]\n"
    '    monkeypatch.setattr(_audio, "AUDIO_ROOT", tmp_path)\n'
    '    monkeypatch.setattr(_audio, "MIX_DIR", tmp_path / "mix")\n'
    "    return tmp_path"
)

NEW = (
    "def _patch_audio_root(tmp_path: Path, monkeypatch) -> Path:\n"
    '    """Override AUDIO_ROOT and MIX_DIR in the audio module.\n'
    "\n"
    "    Uses sys.modules to find the exact module object the top-level\n"
    "    imports resolved to, regardless of import path variant.\n"
    '    """\n'
    "    import sys as _sys\n"
    "    _audio = (\n"
    '        _sys.modules.get("backend.app.services.audio")\n'
    '        or _sys.modules.get("app.services.audio")\n'
    "    )\n"
    "    if _audio is None:\n"
    "        try:\n"
    "            import app.services.audio as _audio  # type: ignore[import]\n"
    "        except ModuleNotFoundError:\n"
    "            import importlib\n"
    '            _audio = importlib.import_module("app.services.audio")\n'
    '    monkeypatch.setattr(_audio, "AUDIO_ROOT", tmp_path)\n'
    '    monkeypatch.setattr(_audio, "MIX_DIR", tmp_path / "mix")\n'
    "    return tmp_path"
)

# Normalise CRLF -> LF for search, then write back
normalised = content.replace("\r\n", "\n")
old_norm = OLD.replace("\r\n", "\n")

if old_norm in normalised:
    fixed = normalised.replace(old_norm, NEW)
    test_path.write_text(fixed, encoding="utf-8")
    print("REPLACED OK")
else:
    print("NOT FOUND — dumping lines 80-90 for debug:")
    for i, ln in enumerate(normalised.splitlines()[78:92], start=79):
        print(f"{i}: {repr(ln)}")
    sys.exit(1)
