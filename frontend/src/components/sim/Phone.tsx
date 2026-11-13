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
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8001";
const WS_BASE = import.meta.env.VITE_WS_BASE ?? "ws://localhost:8001";

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

  const wsRef = useRef<WebSocket | null>(null);
  const seqRef = useRef<number>(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
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
      addLog("info", "WebSocket connected");
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
      addLog("info", `WebSocket closed (code ${ev.code})`);
    };

    ws.onerror = () => {
      addLog("info", "WebSocket error");
    };
  }, [phone, addLog]); // eslint-disable-line

  const sendWs = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      addLog("sent", msg);
      wsRef.current.send(JSON.stringify(msg));
    }
  }, [addLog]);

  // ---------------------------------------------------------------------------
  // Audio playback
  // ---------------------------------------------------------------------------
  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
    if (timeoutTimerRef.current) {
      clearTimeout(timeoutTimerRef.current);
      timeoutTimerRef.current = null;
    }
  }, []);

  const playAudio = useCallback(
    (msg: PlayMsg) => {
      stopAudio();
      setIvrState(msg.state);

      const audio = new Audio(`${API_BASE}${msg.audio_url}`);
      audioRef.current = audio;

      audio.onended = () => {
        // Start timeout timer after audio ends
        const seq = ++seqRef.current;
        timeoutTimerRef.current = setTimeout(() => {
          addLog("info", `Timeout fired (state=${msg.state}, seq=${seq})`);
          sendWs({ t: "timeout", call_id: msg.call_id, seq });
        }, msg.timeout_s * 1000);
      };

      audio.play().catch(() => {
        // Autoplay blocked — still set up timeout
        const seq = ++seqRef.current;
        timeoutTimerRef.current = setTimeout(() => {
          sendWs({ t: "timeout", call_id: msg.call_id, seq });
        }, msg.timeout_s * 1000);
      });
    },
    [stopAudio, sendWs, addLog]
  );

  // ---------------------------------------------------------------------------
  // Server message handler
  // ---------------------------------------------------------------------------
  const handleServerMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const t = msg.t as string;

      if (t === "ring") {
        setPhoneState("ringing");
        setCallId(msg.call_id as string);

      } else if (t === "play") {
        setPhoneState("in_call");
        playAudio(msg as unknown as PlayMsg);

      } else if (t === "hangup") {
        stopAudio();
        setPhoneState("idle");
        setCallId(null);
        setIvrState("");
        stopCallTimer();
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
    connectWs();
    // Give socket a tick to open, then send
    setTimeout(() => {
      sendWs({ t: "missed_call" });
    }, 150);
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
        <p className={`text-sm font-mono font-semibold ${statusColor}`}>{statusText}</p>
        {callTimerText && (
          <p className="text-xs text-gray-500 font-mono mt-1">{callTimerText}</p>
        )}
        {phoneState === "idle" && (
          <button
            className="mt-2 w-full py-2 text-sm bg-green-700 hover:bg-green-600 text-white rounded-lg transition-colors"
            onClick={handleMissedCall}
          >
            📲 Give Missed Call
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
