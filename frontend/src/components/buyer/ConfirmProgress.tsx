// frontend/src/components/buyer/ConfirmProgress.tsx
import React from "react";
import { type BidProgress, formatINR } from "./types";

interface ConfirmProgressProps {
    progress: BidProgress;
    minQtyQtl: number;
    pricePerQtl?: number;
    failed?: boolean;
}

export const ConfirmProgress: React.FC<ConfirmProgressProps> = ({
    progress,
    minQtyQtl,
    pricePerQtl,
    failed = false,
}) => {
    const { accepted_qtl, rejected_qtl, pending_qtl } = progress;
    const total = Math.max(accepted_qtl + rejected_qtl + pending_qtl, 1);

    const accPct = Math.round((accepted_qtl / total) * 100);
    const rejPct = Math.round((rejected_qtl / total) * 100);
    const pendPct = Math.max(0, 100 - accPct - rejPct);

    return (
        <div
            className={`p-4 rounded-xl border space-y-3 ${failed
                    ? "bg-red-50 border-red-200"
                    : "bg-blue-50/60 border-blue-200"
                }`}
        >
            <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    {failed
                        ? "Farmer Confirmation Round Failed"
                        : "Live Farmer Keypad Confirmation"}
                </h3>
                {pricePerQtl && (
                    <span className="text-xs font-semibold text-blue-800">
                        Offer: {formatINR(pricePerQtl)}/qtl
                    </span>
                )}
            </div>

            {/* Horizontal Stacked Progress Bar */}
            <div className="w-full h-4 rounded-full bg-slate-200 overflow-hidden flex">
                {accepted_qtl > 0 && (
                    <div
                        style={{ width: `${accPct}%` }}
                        className="bg-emerald-600 transition-all duration-300"
                        title={`Accepted: ${accepted_qtl} qtl`}
                    />
                )}
                {rejected_qtl > 0 && (
                    <div
                        style={{ width: `${rejPct}%` }}
                        className="bg-slate-400 transition-all duration-300"
                        title={`Rejected: ${rejected_qtl} qtl`}
                    />
                )}
                {pending_qtl > 0 && (
                    <div
                        style={{ width: `${pendPct}%` }}
                        className="bg-amber-400 transition-all duration-300"
                        title={`Pending: ${pending_qtl} qtl`}
                    />
                )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5 font-semibold text-emerald-800">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-600 inline-block" />
                        Accepted: {accepted_qtl} qtl
                    </span>
                    <span className="flex items-center gap-1.5 text-slate-600">
                        <span className="w-2.5 h-2.5 rounded-full bg-slate-400 inline-block" />
                        Rejected: {rejected_qtl} qtl
                    </span>
                    <span className="flex items-center gap-1.5 text-amber-800">
                        <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
                        Pending: {pending_qtl} qtl
                    </span>
                </div>

                <span className="font-semibold text-slate-700">
                    Deal needs &ge; {minQtyQtl} qtl accepted
                </span>
            </div>
        </div>
    );
};