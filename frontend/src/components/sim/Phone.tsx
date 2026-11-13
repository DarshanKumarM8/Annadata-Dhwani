/**
 * Phone.tsx — Browser phone simulator component
 *
 * Implements the full C6 WebSocket protocol:
 *
 *   client → server: { t: "missed_call" }
 *   server → client: { t: "ring", call_id }
 *   client → server: { t: "answer", call_id }
 *   server → client: { t: "play", call_id, audio_url, max_digits, finish_on_key, timeout_s, state }
 *   client → server: { t: "digit", call_id, d, ts_ms, seq }
 *   client → server: { t: "timeout", call_id, seq }
 *   server → client: { t: "hangup", call_id }
 *   client → server: { t: "hangup", call_id }   (red key)
 *
 * Props:
 *   phone   — E.164 phone number for this simulator
 *   label   — Display label (e.g. "Ramesh, Keregodu")
 *
 * Testing switches (passed via props):
 *   injectBounce  — sends every digit twice, the second 30-60 ms later with a new seq
 *   dropCall      — closes the socket without sending hangup, reconnects after 2 s
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Keypad } from "./Keypad";
import { playDtmf } from "./dtmf";
import { API_BASE, WS_BASE } from "../../lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type PhoneState = "idle" | "ringing" | "in_call";

interface LogEntry {
  id: number;
  time: string;
  direction: "sent" | "received" | "info";
  json: string;
}

interface PlayMsg {
  t: "play";
  call_id: string;
  audio_url: string;
  max_digits: number;
  finish_on_key: string;
  timeout_s: number;
  state: string;
}

interface PhoneProps {
  phone: string;
  label: string;
  injectBounce: boolean;
  dropCall: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function timestamp(): string {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function randBetween(a: number, b: number): number {
  return a + Math.random() * (b - a);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
let _logId = 0;

export const Phone: React.FC<PhoneProps> = ({
  phone,
  label,
  injectBounce,
  dropCall,
}) => {
  const [phoneState, setPhoneState] = useState<PhoneState>("idle");
  const [callId, setCallId] = useState<string | null>(null);
  const [ivrState, setIvrState] = useState<string>("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const [callSeconds, setCallSeconds] = useState(0);
  const [connectionState, setConnectionState] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [pendingMissedCall, setPendingMissedCall] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const seqRef = useRef<number>(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const currentPlayRef = useRef<PlayMsg | null>(null);
  const pendingMissedCallRef = useRef(false);
  const missedCallRequestedRef = useRef(false);
  const timeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  // Keep mutable copies for closures
  const injectBounceRef = useRef(injectBounce);
  const dropCallRef = useRef(dropCall);
  useEffect(() => { injectBounceRef.current = injectBounce; }, [injectBounce]);
  useEffect(() => { dropCallRef.current = dropCall; }, [dropCall]);

  // ---------------------------------------------------------------------------
  // Logging
  // ---------------------------------------------------------------------------
  const addLog = useCallback((direction: LogEntry["direction"], data: unknown) => {
    const entry: LogEntry = {
      id: _logId++,
      time: timestamp(),
      direction,
      json: typeof data === "string" ? data : JSON.stringify(data),
    };
    setLog((prev) => [...prev.slice(-199), entry]); // keep last 200
  }, []);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  // ---------------------------------------------------------------------------
  // WebSocket management
  // ---------------------------------------------------------------------------
  const connectWs = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < 2) return; // already open/connecting

    const url = `${WS_BASE}/tel/sim/ws?phone=${encodeURIComponent(phone)}`;
    addLog("info", `Connecting: ${url}`);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current === ws) setConnectionState("connected");
      addLog("info", "WebSocket connected");
      if (pendingMissedCallRef.current) {
        pendingMissedCallRef.current = false;
        const message = { t: "missed_call" };
        addLog("sent", message);
        ws.send(JSON.stringify(message));
      }
    };

    ws.onmessage = (ev) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(ev.data as string);
      } catch {
        addLog("received", ev.data as string);
        return;
      }
      addLog("received", msg);
      handleServerMessage(msg);
    };

    ws.onclose = (ev) => {
      if (wsRef.current === ws) {
        wsRef.current = null;
        pendingMissedCallRef.current = false;
        missedCallRequestedRef.current = false;
        setPendingMissedCall(false);
        setConnectionState("disconnected");
      }
      addLog("info", `WebSocket closed (code ${ev.code})`);
    };

    ws.onerror = () => {
      if (wsRef.current === ws) setConnectionState("disconnected");
      addLog("info", "WebSocket error");
    };
  }, [phone, addLog]); // eslint-disable-line

  const sendWs = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      addLog("sent", msg);
      wsRef.current.send(JSON.stringify(msg));
    } else {
      addLog("info", "Message not sent: WebSocket is not connected");
    }
  }, [addLog]);

  // ---------------------------------------------------------------------------
  // Audio playback
  // ---------------------------------------------------------------------------
  const stopAudio = useCallback(() => {
    if (audioSourceRef.current) {
      audioSourceRef.current.onended = null;
      audioSourceRef.current.stop();
      audioSourceRef.current.disconnect();
      audioSourceRef.current = null;
    }
    if (timeoutTimerRef.current) {
      clearTimeout(timeoutTimerRef.current);
      timeoutTimerRef.current = null;
    }
  }, []);

  const playAudio = useCallback((msg: PlayMsg) => {
      stopAudio();
      currentPlayRef.current = msg;
      setIvrState(msg.state);

      const context = audioContextRef.current;
      if (!context || context.state !== "running") {
        setAudioError("Sound is locked by the browser. Enable sound, then replay this prompt.");
        return;
      }

      void (async () => {
        try {
          const response = await fetch(new URL(msg.audio_url, API_BASE));
          if (!response.ok) throw new Error(`Audio request failed (${response.status}).`);
          const buffer = await context.decodeAudioData(await response.arrayBuffer());
          if (currentPlayRef.current !== msg || context.state !== "running") return;

          const source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(context.destination);
          audioSourceRef.current = source;
          source.onended = () => {
            if (audioSourceRef.current === source) audioSourceRef.current = null;
            if (msg.timeout_s <= 0 || msg.max_digits <= 0) return;
            const seq = ++seqRef.current;
            timeoutTimerRef.current = setTimeout(() => {
              addLog("info", `Timeout fired (state=${msg.state}, seq=${seq})`);
              sendWs({ t: "timeout", call_id: msg.call_id, seq });
            }, msg.timeout_s * 1000);
          };
          setAudioError(null);
          source.start();
        } catch (error) {
          const reason = error instanceof Error ? error.message : "Unknown audio playback error.";
          setAudioError(reason);
          addLog("info", `Audio playback failed: ${reason}`);
        }
      })();
    }, [stopAudio, sendWs, addLog]);

  const enableSound = useCallback(async () => {
    try {
      const context = audioContextRef.current ?? new AudioContext();
      audioContextRef.current = context;
      await context.resume();
      if (context.state !== "running") throw new Error("The browser did not enable audio playback.");
      setSoundEnabled(true);
      setAudioError(null);
      if (currentPlayRef.current) playAudio(currentPlayRef.current);
    } catch (error) {
      const reason = error instanceof Error ? error.message : "Audio could not be enabled.";
      setAudioError(reason);
    }
  }, [playAudio]);

  /**
   * WebSocket protocol — Contract C6 + server extensions:
   *
   *   Known server→client types:
   *     "ring"   – incoming call
   *     "play"   – play audio + collect digits
   *     "hangup" – call ended by server
   *
   *   Extended server→client types (must not crash the simulator):
   *     "info"   – informational, e.g. { t:"info", reason:"DUPLICATE|RATE_LIMITED|BUSY|BUDGET" }
   *
   *   Any other unknown type is shown in the log panel and otherwise ignored.
   */
  const handleServerMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const t = msg.t as string;

      if (t === "ring") {
        missedCallRequestedRef.current = false;
        pendingMissedCallRef.current = false;
        setPendingMissedCall(false);
        setPhoneState("ringing");
        setCallId(msg.call_id as string);

      } else if (t === "play") {
        setPhoneState("in_call");
        playAudio(msg as unknown as PlayMsg);

      } else if (t === "hangup") {
        stopAudio();
        currentPlayRef.current = null;
        setAudioError(null);
        setPhoneState("idle");
        setCallId(null);
        setIvrState("");
        stopCallTimer();

      } else {
        // Unknown / extended message type — log it, never crash.
        // "info" with reason=DUPLICATE|RATE_LIMITED|BUSY|BUDGET arrives here.
        // Already logged by ws.onmessage; nothing else to do.
      }
    },
    [playAudio, stopAudio] // eslint-disable-line
  );

  // ---------------------------------------------------------------------------
  // Call timer
  // ---------------------------------------------------------------------------
  const startCallTimer = useCallback(() => {
    setCallSeconds(0);
    if (callTimerRef.current) clearInterval(callTimerRef.current);
    callTimerRef.current = setInterval(() => setCallSeconds((s) => s + 1), 1000);
  }, []);

  const stopCallTimer = useCallback(() => {
    if (callTimerRef.current) {
      clearInterval(callTimerRef.current);
      callTimerRef.current = null;
    }
    setCallSeconds(0);
  }, []);

  // ---------------------------------------------------------------------------
  // User actions
  // ---------------------------------------------------------------------------
  const handleMissedCall = useCallback(() => {
    if (missedCallRequestedRef.current) return;
    missedCallRequestedRef.current = true;
    setPendingMissedCall(true);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      sendWs({ t: "missed_call" });
      return;
    }
    pendingMissedCallRef.current = true;
    setConnectionState("connecting");
    connectWs();
  }, [connectWs, sendWs]);

  const handleAnswer = useCallback(() => {
    if (!callId) return;
    sendWs({ t: "answer", call_id: callId });
    setPhoneState("in_call");
    startCallTimer();
  }, [callId, sendWs, startCallTimer]);

  const handleHangup = useCallback(() => {
    if (!callId) return;
    stopAudio();
    currentPlayRef.current = null;
    sendWs({ t: "hangup", call_id: callId });
    setPhoneState("idle");
    setCallId(null);
    setIvrState("");
    stopCallTimer();
  }, [callId, stopAudio, sendWs, stopCallTimer]);

  /**
   * "Drop call" testing switch:
   * Close the socket without sending hangup, then reconnect after 2 s.
   */
  const handleDropCall = useCallback(() => {
    stopAudio();
    currentPlayRef.current = null;
    addLog("info", "🔴 DROP CALL — closing socket without hangup");
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setPhoneState("idle");
    setCallId(null);
    setIvrState("");
    stopCallTimer();

    // Reconnect after 2 s in idle state
    reconnectTimerRef.current = setTimeout(() => {
      addLog("info", "Reconnecting after drop...");
      connectWs();
    }, 2000);
  }, [stopAudio, addLog, stopCallTimer, connectWs]);

  /**
   * Digit keypress handler.
   * If injectBounce is on: send the digit twice, second 30-60 ms later.
   * Cancels the timeout timer on any key (C6: "cancel the timer on any key").
   */
  const handleKey = useCallback(
    (key: string) => {
      if (phoneState !== "in_call" || !callId) return;

      // Cancel pending timeout timer on any key
      if (timeoutTimerRef.current) {
        clearTimeout(timeoutTimerRef.current);
        timeoutTimerRef.current = null;
      }

      playDtmf(key);

      const seq1 = ++seqRef.current;
      const digit1 = { t: "digit", call_id: callId, d: key, ts_ms: Date.now(), seq: seq1 };
      sendWs(digit1);

      if (injectBounceRef.current) {
        const delay = randBetween(30, 60);
        setTimeout(() => {
          const seq2 = ++seqRef.current;
          const digit2 = { t: "digit", call_id: callId, d: key, ts_ms: Date.now(), seq: seq2 };
          addLog("info", `↯ BOUNCE: resending ${key} (seq=${seq2}, delay=${delay.toFixed(0)}ms)`);
          sendWs(digit2);
        }, delay);
      }
    },
    [phoneState, callId, sendWs, addLog]
  );

  // Green key: "give missed call" when idle, "answer" when ringing
  const handleGreen = useCallback(() => {
    if (phoneState === "idle") handleMissedCall();
    else if (phoneState === "ringing") handleAnswer();
  }, [phoneState, handleMissedCall, handleAnswer]);

  // Red key: hangup if in call, cancel ring if ringing
  const handleRed = useCallback(() => {
    if (phoneState === "in_call") handleHangup();
    else if (phoneState === "ringing") {
      missedCallRequestedRef.current = false;
      setPendingMissedCall(false);
      setPhoneState("idle");
      setCallId(null);
    }
  }, [phoneState, handleHangup]);

  // ---------------------------------------------------------------------------
  // Cleanup on unmount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    return () => {
      stopAudio();
      stopCallTimer();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      if (audioContextRef.current && audioContextRef.current.state !== "closed") {
        void audioContextRef.current.close();
      }
    };
  }, []); // eslint-disable-line

  // ---------------------------------------------------------------------------
  // Connect on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    connectWs();
  }, [phone]); // eslint-disable-line

  // ---------------------------------------------------------------------------
  // Derived UI values
  // ---------------------------------------------------------------------------
  const statusText =
    phoneState === "idle"
      ? "Idle"
      : phoneState === "ringing"
      ? "⚡ Ringing…"
      : `📞 In Call${ivrState ? ` · ${ivrState}` : ""}`;

  const statusColor =
    phoneState === "idle"
      ? "text-gray-400"
      : phoneState === "ringing"
      ? "text-yellow-400 animate-pulse"
      : "text-green-400";

  const callTimerText =
    phoneState === "in_call"
      ? `${String(Math.floor(callSeconds / 60)).padStart(2, "0")}:${String(callSeconds % 60).padStart(2, "0")}`
      : "";

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="flex flex-col bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-72 overflow-hidden">
      {/* Phone header */}
      <div className="bg-gray-800 px-4 py-3 border-b border-gray-700">
        <p className="text-xs text-gray-400 truncate">{phone}</p>
        <p className="text-sm font-semibold text-white truncate">{label}</p>
      </div>

      {/* Screen */}
      <div className="bg-black px-4 py-3 min-h-[72px] flex flex-col justify-center">
        <p className={`mb-1 text-[10px] ${connectionState === "connected" ? "text-emerald-400" : "text-amber-400"}`}>
          {connectionState === "connected" ? "Connected" : connectionState === "connecting" ? "Connecting to simulator…" : "Disconnected — click the call button to reconnect"}
        </p>
        <p className={`text-sm font-mono font-semibold ${statusColor}`}>{statusText}</p>
        {callTimerText && (
          <p className="text-xs text-gray-500 font-mono mt-1">{callTimerText}</p>
        )}
        {phoneState === "idle" && (
          <button
            className="mt-2 w-full py-2 text-sm bg-green-700 hover:bg-green-600 text-white rounded-lg transition-colors"
            onClick={handleMissedCall}
            disabled={pendingMissedCall}
          >
            {pendingMissedCall ? "Calling…" : "📲 Give Missed Call"}
          </button>
        )}
        {phoneState === "ringing" && (
          <button
            className="mt-2 w-full py-2 text-sm bg-green-500 hover:bg-green-400 text-white rounded-lg animate-pulse transition-colors"
            onClick={handleAnswer}
          >
            ✅ Answer
          </button>
        )}
      </div>

      <div className="border-t border-gray-800 bg-gray-900 px-4 py-2">
        <button
          type="button"
          onClick={() => void enableSound()}
          className="w-full rounded-lg border border-cyan-700 bg-cyan-950/50 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-900/60"
        >
          {soundEnabled ? "Sound enabled — replay prompt" : "Enable sound"}
        </button>
        {audioError && <p className="mt-2 text-xs text-rose-300" role="alert">{audioError}</p>}
        {soundEnabled && currentPlayRef.current && (
          <button
            type="button"
            onClick={() => {
              const prompt = currentPlayRef.current;
              if (prompt) playAudio(prompt);
            }}
            className="mt-2 w-full rounded-lg border border-gray-700 py-1.5 text-xs text-gray-200 hover:bg-gray-800"
          >
            Replay {currentPlayRef.current.state} prompt
          </button>
        )}
      </div>

      {/* Keypad */}
      <div className="flex justify-center py-4 bg-gray-900">
        <Keypad
          onKey={handleKey}
          onGreen={handleGreen}
          onRed={handleRed}
          disabled={phoneState === "idle"}
        />
      </div>

      {/* Drop Call button (always visible for testing) */}
      {phoneState === "in_call" && (
        <div className="px-4 pb-2">
          <button
            className="w-full py-1.5 text-xs bg-red-800 hover:bg-red-700 text-red-200 rounded-lg border border-red-700 transition-colors"
            onClick={handleDropCall}
          >
            ☠️ Drop Call (no hangup)
          </button>
        </div>
      )}

      {/* Message log */}
      <div
        ref={logRef}
        className="border-t border-gray-700 bg-gray-950 h-40 overflow-y-auto font-mono text-[10px] p-2 space-y-0.5"
      >
        {log.length === 0 && (
          <p className="text-gray-600 italic">No messages yet.</p>
        )}
        {log.map((entry) => (
          <div
            key={entry.id}
            className={
              entry.direction === "sent"
                ? "text-cyan-400"
                : entry.direction === "received"
                ? "text-yellow-300"
                : "text-gray-500 italic"
            }
          >
            <span className="text-gray-600">{entry.time} </span>
            {entry.direction === "sent" && "→ "}
            {entry.direction === "received" && "← "}
            {entry.json}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Phone;
