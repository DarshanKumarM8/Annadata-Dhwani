/**
 * Keypad.tsx — 3×4 DTMF keypad for the phone simulator
 *
 * Layout:
 *   1  2  3
 *   4  5  6
 *   7  8  9
 *   *  0  #
 *   [green] [red]
 *
 * Props:
 *   onKey(key)       — called on every digit / symbol keypress
 *   onGreen()        — green key pressed (depends on call state)
 *   onRed()          — red key pressed (hangup / cancel)
 *   disabled         — grey out the whole keypad
 */

import React from "react";

interface KeypadProps {
  onKey: (key: string) => void;
  onGreen: () => void;
  onRed: () => void;
  disabled?: boolean;
}

const KEYS: (string | null)[][] = [
  ["1", "2", "3"],
  ["4", "5", "6"],
  ["7", "8", "9"],
  ["*", "0", "#"],
];

const KEY_LABELS: Record<string, string> = {
  "1": "1",   "2": "2 ABC", "3": "3 DEF",
  "4": "4 GHI","5": "5 JKL", "6": "6 MNO",
  "7": "7 PQRS","8": "8 TUV","9": "9 WXYZ",
  "*": "✱",   "0": "0 +",   "#": "#",
};

export const Keypad: React.FC<KeypadProps> = ({
  onKey,
  onGreen,
  onRed,
  disabled = false,
}) => {
  const btnBase =
    "flex flex-col items-center justify-center rounded-full w-14 h-14 select-none " +
    "text-sm font-semibold transition-transform active:scale-95 ";

  const digitBtn =
    btnBase +
    (disabled
      ? "bg-gray-200 text-gray-400 cursor-not-allowed"
      : "bg-gray-700 text-white hover:bg-gray-600 cursor-pointer shadow");

  return (
    <div className={`flex flex-col items-center gap-2 ${disabled ? "opacity-60" : ""}`}>
      {/* Digit rows */}
      {KEYS.map((row, ri) => (
        <div key={ri} className="flex gap-3">
          {row.map((key) =>
            key === null ? (
              <div key="empty" className="w-14 h-14" />
            ) : (
              <button
                key={key}
                className={digitBtn}
                disabled={disabled}
                onClick={() => !disabled && onKey(key)}
                aria-label={`Key ${key}`}
              >
                <span className="text-base leading-none">{key}</span>
                {KEY_LABELS[key] !== key && (
                  <span className="text-[9px] mt-0.5 opacity-70 leading-none">
                    {KEY_LABELS[key].replace(key, "").trim()}
                  </span>
                )}
              </button>
            )
          )}
        </div>
      ))}

      {/* Green / Red action keys */}
      <div className="flex gap-3 mt-1">
        {/* Green — call / answer */}
        <button
          className={
            btnBase +
            (disabled
              ? "bg-gray-300 text-gray-400 cursor-not-allowed"
              : "bg-green-500 text-white hover:bg-green-400 cursor-pointer shadow-lg shadow-green-800/30")
          }
          disabled={disabled}
          onClick={() => !disabled && onGreen()}
          aria-label="Green key"
        >
          <span className="text-xl">📞</span>
        </button>

        {/* Empty middle space */}
        <div className="w-14 h-14" />

        {/* Red — hangup */}
        <button
          className={
            btnBase +
            (disabled
              ? "bg-gray-300 text-gray-400 cursor-not-allowed"
              : "bg-red-500 text-white hover:bg-red-400 cursor-pointer shadow-lg shadow-red-800/30")
          }
          disabled={disabled}
          onClick={() => !disabled && onRed()}
          aria-label="Red key (hang up)"
        >
          <span className="text-xl">📵</span>
        </button>
      </div>
    </div>
  );
};

export default Keypad;
