// frontend/src/components/buyer/ClusterList.tsx
import React, { useEffect, useState } from "react";
import { Cluster, ClusterStatus, formatINR } from "./types";

interface ClusterListProps {
    clusters: Cluster[];
    selectedId?: string;
    onSelect: (id: string) => void;
    selectedStatuses: ClusterStatus[];
    onToggleStatus: (status: ClusterStatus) => void;
    selectedCrop: string;
    onCropChange: (crop: string) => void;
}

const ALL_STATUSES: ClusterStatus[] = [
    "OPEN",
    "READY",
    "BIDDING",
    "CONFIRMING",
    "DEAL",
];

export const STATUS_COLORS: Record<ClusterStatus, string> = {
    OPEN: "bg-slate-100 text-slate-700 border-slate-300",
    READY: "bg-amber-100 text-amber-800 border-amber-300",
    BIDDING: "bg-emerald-100 text-emerald-800 border-emerald-400",
    CONFIRMING: "bg-blue-100 text-blue-800 border-blue-300",
    DEAL: "bg-purple-100 text-purple-800 border-purple-300",
    CLOSED: "bg-gray-100 text-gray-600 border-gray-300",
    NO_BID: "bg-red-50 text-red-700 border-red-200",
    FAILED: "bg-red-100 text-red-800 border-red-300",
};

export function formatCountdown(biddingEndsAt: string | null, nowMs: number): string {
    if (!biddingEndsAt) return "—";
    const diffSec = Math.floor((new Date(biddingEndsAt).getTime() - nowMs) / 1000);
    if (diffSec <= 0) return "ended";
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    if (mins >= 60) {
        const hrs = Math.floor(mins / 60);
        const remMins = mins % 60;
        return `${hrs}h ${remMins}m ${secs}s`;
    }
    return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}

export const ClusterList: React.FC<ClusterListProps> = ({
    clusters,
    selectedId,
    onSelect,
    selectedStatuses,
    onToggleStatus,
    selectedCrop,
    onCropChange,
}) => {
    const [nowMs, setNowMs] = useState<number>(() => Date.now());

    useEffect(() => {
        const timer = setInterval(() => setNowMs(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);

    const uniqueCrops = Array.from(
        new Set(clusters.map((c) => c.crop_code))
    ).map((code) => {
        const match = clusters.find((c) => c.crop_code === code);
        return { code, name: match?.crop_name || code };
    });

    const filtered = clusters.filter((c) => {
        const statusOk =
            selectedStatuses.length === 0 || selectedStatuses.includes(c.status);
        const cropOk = !selectedCrop || c.crop_code === selectedCrop;
        return statusOk && cropOk;
    });

    return (
        <div className="flex flex-col h-full bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {/* Filter Header */}
            <div className="p-4 border-b border-slate-200 bg-slate-50 space-y-3">
                <div className="flex items-center justify-between gap-2">
                    <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                        Pooled Clusters ({filtered.length})
                    </h2>
                    <select
                        value={selectedCrop}
                        onChange={(e) => onCropChange(e.target.value)}
                        className="text-sm border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-600"
                    >
                        <option value="">All Crops</option>
                        {uniqueCrops.map((crop) => (
                            <option key={crop.code} value={crop.code}>
                                {crop.name}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Multi-select Status Filter Chips */}
                <div className="flex flex-wrap gap-1.5">
                    {ALL_STATUSES.map((st) => {
                        const active = selectedStatuses.includes(st);
                        return (
                            <button
                                key={st}
                                type="button"
                                onClick={() => onToggleStatus(st)}
                                className={`text-xs font-medium px-2.5 py-1 rounded-full border transition ${active
                                    ? "bg-emerald-700 text-white border-emerald-700 shadow-xs"
                                    : "bg-white text-slate-600 border-slate-300 hover:bg-slate-100"
                                    }`}
                            >
                                {st}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Cards List */}
            <div className="flex-1 overflow-y-auto divide-y divide-slate-100 p-3 space-y-2.5">
                {filtered.length === 0 ? (
                    <div className="py-12 text-center text-sm text-slate-500">
                        No clusters match the selected filters.
                    </div>
                ) : (
                    filtered.map((c) => {
                        const isSelected = c.id === selectedId;
                        const tonnes = (c.total_qtl / 10).toFixed(1);
                        const countdown = formatCountdown(c.bidding_ends_at, nowMs);

                        return (
                            <div
                                key={c.id}
                                onClick={() => onSelect(c.id)}
                                className={`p-3.5 rounded-xl border transition cursor-pointer ${isSelected
                                    ? "border-emerald-600 bg-emerald-50/50 ring-2 ring-emerald-600/20"
                                    : "border-slate-200 hover:border-slate-300 bg-white"
                                    }`}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs font-mono font-semibold text-slate-500">
                                                C-{c.code}
                                            </span>
                                            <h3 className="text-base font-bold text-slate-900">
                                                {c.crop_name}
                                            </h3>
                                            {c.grade && (
                                                <span className="text-xs font-bold px-2 py-0.5 rounded bg-emerald-700 text-white">
                                                    Grade {c.grade}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-xs text-slate-600 mt-0.5">
                                            {c.collection_point.name} · {c.district}
                                        </p>
                                    </div>

                                    <span
                                        className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${STATUS_COLORS[c.status] || "bg-gray-100 text-gray-700"
                                            }`}
                                    >
                                        {c.status}
                                    </span>
                                </div>

                                <div className="mt-3 grid grid-cols-3 gap-2 pt-2.5 border-t border-slate-100 text-xs">
                                    <div>
                                        <span className="text-slate-500 block">Volume & Lots</span>
                                        <span className="font-semibold text-slate-900">
                                            {tonnes} t · {c.total_qtl} qtl
                                        </span>
                                        <span className="text-slate-500 block">
                                            {c.listing_count} lots
                                        </span>
                                    </div>

                                    <div>
                                        <span className="text-slate-500 block">Min / Avg Ask</span>
                                        <span className="font-semibold text-slate-900">
                                            {formatINR(c.min_ask)} / {formatINR(c.wavg_ask)}
                                        </span>
                                    </div>

                                    <div className="text-right">
                                        <span className="text-slate-500 block">Best Bid</span>
                                        {c.best_bid ? (
                                            <span className="font-bold text-emerald-700">
                                                {formatINR(c.best_bid.price_per_qtl)}
                                                {c.best_bid.mine ? " (You)" : ""}
                                            </span>
                                        ) : (
                                            <span className="text-slate-400 italic">no bids</span>
                                        )}
                                        {c.bidding_ends_at && c.status === "BIDDING" && (
                                            <span
                                                className={`block font-mono text-[11px] mt-0.5 ${countdown === "ended"
                                                    ? "text-red-600 font-semibold"
                                                    : "text-amber-700"
                                                    }`}
                                            >
                                                ⏱ {countdown}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
};