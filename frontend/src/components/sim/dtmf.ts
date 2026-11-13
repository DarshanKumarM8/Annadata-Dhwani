/**
 * dtmf.ts — WebAudio DTMF tone generation
 *
 * Standard DTMF frequency pairs:
 *   Row frequencies:    697, 770, 852, 941 Hz
 *   Column frequencies: 1209, 1336, 1477 Hz
 *
 * Key layout:
 *   1 2 3
 *   4 5 6
 *   7 8 9
 *   * 0 #
 */

const ROW_FREQ: Record<string, number> = {
  "1": 697, "2": 697, "3": 697,
  "4": 770, "5": 770, "6": 770,
  "7": 852, "8": 852, "9": 852,
  "*": 941, "0": 941, "#": 941,
};

const COL_FREQ: Record<string, number> = {
  "1": 1209, "2": 1336, "3": 1477,
  "4": 1209, "5": 1336, "6": 1477,
  "7": 1209, "8": 1336, "9": 1477,
  "*": 1209, "0": 1336, "#": 1477,
};

const TONE_DURATION_S = 0.100; // 100 ms
const GAIN_VALUE = 0.1;

let _ctx: AudioContext | null = null;

function getContext(): AudioContext {
  if (!_ctx || _ctx.state === "closed") {
    _ctx = new AudioContext();
  }
  return _ctx;
}

/**
 * Play a DTMF tone for the given key (100 ms, gain 0.1).
 * No-ops for unknown keys.
 */
export function playDtmf(key: string): void {
  const rowF = ROW_FREQ[key];
  const colF = COL_FREQ[key];
  if (!rowF || !colF) return;

  try {
    const ctx = getContext();
    // Resume if suspended (browser autoplay policy)
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }

    const now = ctx.currentTime;
    const gainNode = ctx.createGain();
    gainNode.gain.setValueAtTime(GAIN_VALUE, now);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + TONE_DURATION_S);
    gainNode.connect(ctx.destination);

    for (const freq of [rowF, colF]) {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now);
      osc.connect(gainNode);
      osc.start(now);
      osc.stop(now + TONE_DURATION_S);
    }
  } catch {
    // Audio not available — silently ignore
  }
}
