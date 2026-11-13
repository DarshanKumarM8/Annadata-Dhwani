# Audio Test Report — Annadata Dhwani (H6)

**Task:** H6 — Handset Noise Test  
**Owner:** Hitesh (Voice AI & Network Physics)  
**Project:** Annadata Dhwani · Seva First Innovation Challenge 2026 · Debug4X team  
**Contract clause:** §6 of TASK_DIVISION.md — "play 10 mixed prompts on a real phone, verify 10/10 numbers heard correctly"

---

## 1. Automated Pipeline Verification (Pre-Handset)

These checks run without a physical phone. All must pass before handset testing.

### 1a. Audio Clip Integrity

```
python backend/scripts/prewarm_audio.py --langs en --check
```

| Metric | Expected | Result |
|---|---|---|
| Total clips | 108 | **108** ✅ |
| Missing | 0 | **0** ✅ |
| Bad (wrong sample rate / channels / depth) | 0 | **0** ✅ |
| Sample rate | 8000 Hz | **8000 Hz** ✅ |
| Channels | Mono (1) | **1** ✅ |
| Bit depth | 16-bit PCM | **pcm_s16le** ✅ |
| Voice (English) | en-IN-NeerjaNeural | **en-IN-NeerjaNeural** ✅ |

**Run date:** 2026-11-13 · **Run by:** Hitesh

### 1b. Unit Test Suite (audio.py — Contract C9)

```
python -m pytest backend/tests/test_audio.py -v -p no:langsmith
```

| Test class | Tests | Result |
|---|---|---|
| TestDigitClips | 6 | **6/6 PASS** ✅ |
| TestMixDuration | 4 | **4/4 PASS** ✅ |
| TestCacheHit | 3 | **3/3 PASS** ✅ |
| TestLangOverridePrefix | 3 | **3/3 PASS** ✅ |
| TestMissingClip | 4 | **4/4 PASS** ✅ |
| TestConcurrency (20 threads) | 1 | **1/1 PASS** ✅ |
| TestMixUrl | 3 | **3/3 PASS** ✅ |
| **TOTAL** | **24** | **24/24 PASS** ✅ |

**Run date:** 2026-11-13 · **Run by:** Hitesh

### 1c. Phone Simulator UI (H5 — Contract C6)

| Check | Result |
|---|---|
| Page loads at `/sim` | ✅ |
| Two phones side-by-side (Ramesh +91980…001, Lakshmi +91980…002) | ✅ |
| Keypad 0–9, *, # | ✅ |
| "Give Missed Call" button | ✅ |
| "Inject key bounce" toggle | ✅ |
| "Drop call" appears during live call | ✅ |
| No JS crashes | ✅ |
| WebSocket reconnects after `code 1006` | ✅ |

---

## 2. Handset Noise Test (H6 — Manual)

### 2a. Test Setup

| Item | Value |
|---|---|
| Test environment | Real handset + background noise (café / farm) |
| Audio output method | Exotel IVR callback **OR** speaker playback via backend `/audio/mix/<sha>.wav` |
| Pass criterion | Listener hears the number correctly on first attempt, no replay needed |
| Fail criterion | Mishear, need replay, or number is inaudible |
| Scorer | Hitesh |

**Equipment checklist before test:**
- [ ] Android/iOS handset with SIM (or Exotel test call)
- [ ] Background noise source active (fan / street audio / ~55 dB ambient)
- [ ] `backend/` server running (`python -m uvicorn app.main:app --reload`)
- [ ] `audio/en/*.wav` present (108 clips verified above)

---

### 2b. The 10 Test Prompts

Each test plays a **mixed sequence** via `audio.py mix()`. The scorer listens and records what they heard.

| # | Clip sequence | Expected spoken output | Heard | Pass? | Notes |
|---|---|---|---|---|---|
| 1 | `welcome` | "Welcome to Annadata Dhwani." | | ☐ | Intro clarity |
| 2 | `ask_qty` | "Please enter the quantity in quintals." | | ☐ | Instruction clarity |
| 3 | `you_entered` + `d_4` + `d_2` | "You entered… four… two." | | ☐ | Digit read-back |
| 4 | `mandi_price_was` + `d_2` + `d_4` + `d_0` + `d_0` | "The mandi price was… two… four… zero… zero." | | ☐ | 4-digit price |
| 5 | `fair_price_is` + `d_2` + `d_6` + `d_5` + `d_0` + `rupees_per_qtl` | "The fair price is… two… six… five… zero… rupees per quintal." | | ☐ | Full price sentence |
| 6 | `qty_7` | "Seven." | | ☐ | Single qty clip |
| 7 | `qty_25` | "Twenty-five." | | ☐ | Two-word number |
| 8 | `your_number_is` + `d_4` + `d_2` + `d_7` | "Your listing number is… four… two… seven." | | ☐ | Listing code (3 digits) |
| 9 | `offer_intro` + `for_your` + `crop_ragi` + `at_price` + `d_3` + `d_1` + `d_0` + `d_0` | "New offer… for your… ragi… at price… three… one… zero… zero." | | ☐ | Full offer announcement |
| 10 | `bad_input` + `main_menu` | "I didn't understand that. Main menu: press 1 for new listing…" | | ☐ | Error recovery prompt |

---

### 2c. Results Log

| Test | Date | Ambient noise level | Handset | Pass/Fail | Heard (write verbatim) |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | |
| 8 | | | | | |
| 9 | | | | | |
| 10 | | | | | |

**Score: __ / 10**  
**Signed off by:** _______________  
**Date:** _______________

---

### 2d. How to Play a Test Prompt (Local Playback)

If Exotel is not yet connected, play clips directly from the backend:

```bash
# Start backend in one terminal
cd backend
python -m uvicorn app.main:app --reload --port 8000

# In another terminal — get the mix URL for test #5
python - <<'EOF'
import sys; sys.path.insert(0, ".")
from app.services.audio import mix_url
clips = ["fair_price_is", "d_2", "d_6", "d_5", "d_0", "rupees_per_qtl"]
print(mix_url(clips, "en", "http://localhost:8000"))
EOF

# Open the printed URL in a browser or:
# curl <url> --output test5.wav && ffplay test5.wav
```

---

## 3. Jury Q&A Pack (H8)

Answers to expected jury questions about the audio pipeline.

### Q1: Why 8 kHz / mono / 16-bit PCM?

This matches the codec used by **Exotel's IVR telephony** (G.711 µ-law / a-law, 8 kHz). Sending higher-quality audio wastes bandwidth and is re-sampled down anyway, potentially introducing artefacts. Our FFmpeg filter chain:

```
highpass=f=300  — removes low-frequency hum (wind, handling noise)
lowpass=f=3400  — removes high-frequency hiss above phone speech band (300–3400 Hz)
loudnorm=I=-16:TP=-3:LRA=7  — ITU-R BS.1770-3 loudness normalisation to -16 LUFS
-ar 8000 -ac 1 -c:a pcm_s16le — 8 kHz mono 16-bit PCM output
```

This produces audio that is perceptually clear on a 2G voice call.

### Q2: Why edge-tts instead of Bhashini?

Bhashini API approval was pending at hackathon start. **edge-tts** (Microsoft Azure neural TTS via Python) is:
- Zero-approval, zero-cost for prototyping
- Supports `kn-IN-SapnaNeural` and `hi-IN-SwaraNeural` natively
- Produces natural-sounding speech at ≤2 s per clip

The architecture is **language-agnostic**: voice is a CLI parameter (`--voices lang:VoiceName`), not hardcoded. Swapping to Bhashini or any other TTS engine only changes `prewarm_audio.py`; `audio.py` and all API contracts remain unchanged.

### Q3: How do farmers in low-connectivity areas hear the audio?

The IVR audio plays **during the voice call itself** (Exotel streams it). No smartphone or internet is required on the farmer's side — a basic 2G feature phone is sufficient. The 8 kHz band-limited audio is optimised for exactly this channel.

### Q7: What prevents audio quality degradation over multiple network hops?

1. **Pre-rendered WAVs** — no real-time synthesis during the call. All clips are generated ahead of time and verified with `--check`.
2. **Atomic writes** — `audio.py` writes mixed files via `tempfile → os.replace`, preventing partial reads.
3. **Cache** — mixed sequences are SHA-keyed; identical prompts are served from disk without re-mixing.
4. **Loudness normalisation** — the `loudnorm` filter ensures consistent perceived volume regardless of the TTS voice's natural output level.

---

## 4. Files Owned by This Task

| File | Purpose | Status |
|---|---|---|
| `backend/prompts.yaml` | 108 clip definitions (en text + reviewed flag) | ✅ Done |
| `backend/scripts/prewarm_audio.py` | edge-tts synthesis + FFmpeg conversion | ✅ Done |
| `backend/app/services/audio.py` | Contract C9 mixer (digit_clips, mix, mix_url, missing_clips) | ✅ Done |
| `backend/tests/test_audio.py` | 24 pytest tests, all passing | ✅ Done |
| `frontend/src/routes/Sim.tsx` | Phone simulator route | ✅ Done |
| `frontend/src/components/sim/Phone.tsx` | Phone component (Contract C6) | ✅ Done |
| `frontend/src/components/sim/Keypad.tsx` | DTMF keypad | ✅ Done |
| `frontend/src/components/sim/dtmf.ts` | WebAudio DTMF tone generator | ✅ Done |
| `audio/en/*.wav` | 108 English audio clips (8000 Hz / mono / 16-bit) | ✅ Done |
| `docs/audio_tests.md` | This file — H6 handset test log + H8 jury Q&A | ✅ Done |

---

## 5. Remaining Manual Steps (H6, H7, H9)

| Task | Description | Status |
|---|---|---|
| H6 | Complete Section 2c above on a real handset | ⏳ Needs handset |
| H7 | Record 3-min demo video (screen + voice) | ⏳ After CP3 |
| H9 | Rehearse jury Q&A with team | ⏳ After CP3 |

**Blockers:**
- E2E handset test needs Darshan's WS endpoint at `ws://localhost:8000/tel/sim/ws`
- Kannada/Hindi clips need native speaker to fill `prompts.yaml` translations, then run:  
  `python backend/scripts/prewarm_audio.py --langs kn,hi --voices kn:kn-IN-SapnaNeural,hi:hi-IN-SwaraNeural`
