/**
 * Sim.tsx — Browser Phone Simulator route
 *
 * Mounts two Phone components side by side, each driven by a seeded
 * farmer from the demo dataset.
 *
 * Testing switches (global, applied to both phones):
 *   "Inject key bounce" — sends every digit twice (second 30-60 ms later, new seq)
 *   "Drop call"        — in-phone button: closes socket without hangup, reconnects after 2 s
 *
 * Farmer phone selector: each phone has its own dropdown of seeded demo farmers.
 * Farmers are defined as a const array in this file (editable later).
 *
 * Contract C6 protocol is fully implemented inside Phone.tsx.
 */

import React, { useState } from "react";
import { Phone } from "../components/sim/Phone";

// ---------------------------------------------------------------------------
// Seeded demo farmer data (edit these to match db/002_reference.sql seeds)
// ---------------------------------------------------------------------------
const DEMO_FARMERS: { phone: string; label: string }[] = [
  { phone: "+919800000001", label: "Ramesh, Keregodu" },
  { phone: "+919800000002", label: "Lakshmi, Keregodu" },
  { phone: "+919800000003", label: "Manju, Hosahalli" },
  { phone: "+919800000004", label: "Savitha, Hosahalli" },
  { phone: "+919800000005", label: "Krishnappa, Keregodu" },
  { phone: "+919800000006", label: "Meena, Hosahalli" },
  { phone: "+919800000007", label: "Rajesh, Keregodu" },
  { phone: "+919800000008", label: "Geetha, Hosahalli" },
];

// ---------------------------------------------------------------------------
// FarmerSelector — per-phone dropdown
// ---------------------------------------------------------------------------
interface FarmerSelectorProps {
  value: string;
  onChange: (phone: string) => void;
  id: string;
}

const FarmerSelector: React.FC<FarmerSelectorProps> = ({ value, onChange, id }) => (
  <div className="mb-2 px-1">
    <label
      htmlFor={id}
      className="block text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide"
    >
      Farmer
    </label>
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full text-sm bg-gray-800 border border-gray-600 text-white rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-cyan-500"
    >
      {DEMO_FARMERS.map((f) => (
        <option key={f.phone} value={f.phone}>
          {f.label} · {f.phone}
        </option>
      ))}
    </select>
  </div>
);

// ---------------------------------------------------------------------------
// Sim route
// ---------------------------------------------------------------------------
export const Sim: React.FC = () => {
  // Global testing switches
  const [injectBounce, setInjectBounce] = useState(false);

  // Per-phone farmer selection
  const [farmer1, setFarmer1] = useState(DEMO_FARMERS[0].phone);
  const [farmer2, setFarmer2] = useState(DEMO_FARMERS[1].phone);

  const farmerLabel = (phone: string) =>
    DEMO_FARMERS.find((f) => f.phone === phone)?.label ?? phone;

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white tracking-tight">
          📱 Phone Simulator
        </h1>
        <p className="text-sm text-gray-400 mt-1">
          Annadata Dhwani · Browser IVR test tool · Contract C6
        </p>
      </div>

      {/* Global Controls */}
      <div className="mb-6 flex flex-wrap gap-4 items-center bg-gray-900 border border-gray-700 rounded-xl px-5 py-3">
        <span className="text-sm font-semibold text-gray-300">🧪 Testing switches:</span>

        {/* Inject key bounce toggle */}
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <div
            className={`relative w-10 h-5 rounded-full transition-colors ${
              injectBounce ? "bg-orange-500" : "bg-gray-600"
            }`}
            onClick={() => setInjectBounce((v) => !v)}
            role="checkbox"
            aria-checked={injectBounce}
            tabIndex={0}
            onKeyDown={(e) => e.key === " " && setInjectBounce((v) => !v)}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                injectBounce ? "translate-x-5" : ""
              }`}
            />
          </div>
          <span className="text-sm text-gray-200">
            Inject key bounce
            {injectBounce && (
              <span className="ml-1.5 text-orange-400 font-semibold">(ON)</span>
            )}
          </span>
        </label>

        {/* Info about drop call */}
        <span className="text-xs text-gray-500 ml-2 border-l border-gray-700 pl-3">
          "Drop call" button appears on each phone during a live call.
        </span>
      </div>

      {/* Bounce explanation */}
      {injectBounce && (
        <div className="mb-4 px-4 py-2 bg-orange-900/40 border border-orange-700 rounded-lg text-xs text-orange-300">
          ↯ <strong>Bounce mode active:</strong> every digit key will be sent <em>twice</em>. The second copy
          arrives 30–60 ms later with a new <code>seq</code>. Watch the debouncer on the backend ops screen.
        </div>
      )}

      {/* Two phones side by side */}
      <div className="flex flex-col lg:flex-row gap-6 items-start justify-center">
        {/* Phone 1 */}
        <div className="flex flex-col gap-2">
          <FarmerSelector
            id="farmer-1"
            value={farmer1}
            onChange={setFarmer1}
          />
          <Phone
            key={farmer1 + "_1"}
            phone={farmer1}
            label={farmerLabel(farmer1)}
            injectBounce={injectBounce}
            dropCall={false}
          />
        </div>

        {/* Divider */}
        <div className="hidden lg:flex items-center self-stretch">
          <div className="w-px bg-gray-800 h-full mx-2" />
        </div>

        {/* Phone 2 */}
        <div className="flex flex-col gap-2">
          <FarmerSelector
            id="farmer-2"
            value={farmer2}
            onChange={setFarmer2}
          />
          <Phone
            key={farmer2 + "_2"}
            phone={farmer2}
            label={farmerLabel(farmer2)}
            injectBounce={injectBounce}
            dropCall={false}
          />
        </div>
      </div>

      {/* Footer notes */}
      <div className="mt-8 text-xs text-gray-600 text-center space-y-1">
        <p>
          WebSocket: <code className="text-gray-500">{import.meta.env.VITE_WS_BASE ?? "ws://localhost:8001"}/tel/sim/ws?phone=…</code>
        </p>
        <p>
          Audio base: <code className="text-gray-500">{import.meta.env.VITE_API_BASE ?? "http://localhost:8001"}</code>
        </p>
        <p className="text-gray-700">Log colour: <span className="text-cyan-400">cyan = sent</span> · <span className="text-yellow-300">yellow = received</span> · <span className="text-gray-500">grey = info</span></p>
      </div>
    </div>
  );
};

export default Sim;
