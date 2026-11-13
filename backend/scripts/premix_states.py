"""
premix_states.py - Generates state-named audio WAVs in audio/mix/ for simulator and demo.
"""
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.audio import mix, AUDIO_ROOT, MIX_DIR

MIX_DIR.mkdir(parents=True, exist_ok=True)

STATE_CLIPS = {
    "lang.wav": (["welcome", "kn:lang_option", "hi:lang_option", "en:lang_option"], "kn"),
    "consent.wav": (["consent"], "kn"),
    "crop.wav": (["crop_menu_intro", "cropkey_ragi_1", "cropkey_paddy_common_2", "cropkey_maize_3", "helper_key_0"], "kn"),
    "qty.wav": (["ask_qty"], "kn"),
    # QTY_CONFIRM and FINAL include the caller's entered quantity and are mixed at runtime.
    "price.wav": (["fair_price_is", "d_2", "d_1", "d_0", "d_0", "rupees_per_qtl", "ask_price"], "kn"),
    "guard.wav": (["guard_warn", "d_2", "d_1", "d_0", "d_0", "rupees_per_qtl", "guard_options"], "kn"),
    "done.wav": (["listed_ok", "your_number_is", "d_1", "d_0", "d_1", "will_call"], "kn"),
}

def generate_all():
    for filename, (clips, lang) in STATE_CLIPS.items():
        sha = mix(clips, lang)
        source = MIX_DIR / f"{sha}.wav"
        target = MIX_DIR / filename
        shutil.copyfile(source, target)
        print(f"  ✓ {filename} ({len(clips)} clips) -> {target.name}")

if __name__ == "__main__":
    generate_all()
    print("Done pre-mixing all simulator states.")
