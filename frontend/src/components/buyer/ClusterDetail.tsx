// frontend/src/components/buyer/ClusterDetail.tsx
import React, { useEffect, useState } from "react";
import {
    type BidProgress,
    type ClusterDetailData,
    type DealStatus,
    formatINR,
    type MyBid,
    type MyDeal,
    type PriceBasis,
} from "./types";
import { STATUS_COLORS, formatCountdown } from "./ClusterList";
import { BidForm } from "./BidForm";
import { ConfirmProgress } from "./ConfirmProgress";
import { DealCard } from "./DealCard";

interface ClusterDetailProps {
    detail: ClusterDetailData | null;
    loading: boolean;
    error: string | null;
    myBid?: MyBid | null;
    myDeal?: MyDeal | null;
    liveProgress?: BidProgress | null;
    bidFailedInfo?: { accepted_qtl: number; min_qty_qtl: number } | null;
    onBidSuccess: (bid: MyBid) => void;
    onDealStatusChange: (dealId: string, newStatus: DealStatus) => void;
}

function formatBasisLabel(basis: PriceBasis, priceDate: string): string {
    switch (basis) {
        case "DISTRICT_FRESH":
            return `mandi price on ${priceDate}`;
        case "DISTRICT_7D":
            return "7-day district average";
        case "STATE_7D":
            return "7-day state average";
        default:
            return priceDate;
    }
}

export const ClusterDetail: React.FC<ClusterDetailProps> = ({
    detail,
    loading,
    error,
    myBid,
    myDeal,
    liveProgress,
    bidFailedInfo,
    onBidSuccess,
    onDealStatusChange,
}) => {
    const [nowMs, setNowMs] = useState<number>(() => Date.now());
    const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8001";

    useEffect(() => {
        const timer = setInterval(() => setNowMs(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);

    if (loading) {
        return (
            <div className="h-full bg-white rounded-xl border border-slate-200 p-8 flex items-center justify-center text-sm text-slate-500">
                Loading cluster details...
            </div>
        );
    }

    if (error) {
        return (
            <div className="h-full bg-white rounded-xl border border-red-200 p-8 flex items-center justify-center text-sm text-red-600">
                {error}
            </div>
        );
    }

    if (!detail) {
        return (
            <div className="h-full bg-white rounded-xl border border-slate-200 p-8 flex items-center justify-center text-sm text-slate-500">
                Select a cluster from the left list to view lots, FPO verification, and place bids.
            </div>
        );
    }

    const tonnes = (detail.total_qtl / 10).toFixed(1);
    const countdown = formatCountdown(detail.bidding_ends_at, nowMs);
    const fullPhotoUrl = detail.photo_url
        ? detail.photo_url.startsWith("http")
            ? detail.photo_url
            : `${apiBase}${detail.photo_url}`
        : null;

    const activeProgress = liveProgress || myBid?.progress || null;
    const minQtyTarget =
        bidFailedInfo?.min_qty_qtl || myBid?.min_qty_qtl || detail.total_qtl;

    return (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
            {/* Top Header */}
            <div className="p-5 border-b border-slate-200 bg-slate-50 flex flex-wrap items-start justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2.5">
                        <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                            C-{detail.code}
                        </span>
                        <h2 className="text-xl font-bold text-slate-900">
                            {detail.crop_name}
                        </h2>
                        {detail.grade && (
                            <span className="text-xs font-bold px-2.5 py-0.5 rounded bg-emerald-700 text-white">
                                Grade {detail.grade}
                            </span>
                        )}
                        <span
                            className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${STATUS_COLORS[detail.status]
                                }`}
                        >
                            {detail.status}
                        </span>
                    </div>
                    <p className="text-sm text-slate-600 mt-1">
                        📍 <strong>{detail.collection_point.name}</strong> ({detail.district}) ·{" "}
                        <span className="font-semibold text-slate-800">
                            {tonnes} t · {detail.total_qtl} qtl
                        </span>{" "}
                        across {detail.listing_count} farmer lots
                    </p>
                </div>

                <div className="text-right">
                    <div className="text-xs text-slate-500">Current Best Bid</div>
                    <div className="text-lg font-bold text-emerald-700">
                        {detail.best_bid ? (
                            <>
                                {formatINR(detail.best_bid.price_per_qtl)}/qtl
                                {detail.best_bid.mine && (
                                    <span className="ml-1.5 text-xs bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded">
                                        Your Bid
                                    </span>
                                )}
                            </>
                        ) : (
                            <span className="text-slate-400 font-normal text-sm">No bids yet</span>
                        )}
                    </div>
                    {detail.bidding_ends_at && (
                        <div className="text-xs font-mono text-amber-700 mt-0.5">
                            Auction window: <strong>{countdown}</strong>
                        </div>
                    )}
                </div>
            </div>

            {/* Main Content Body */}
            <div className="p-5 overflow-y-auto space-y-5 flex-1">
                {/* Price Reference & FPO Verification Photo Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Price Reference Box */}
                    <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 space-y-2">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-amber-900">
                                Reference Prices (₹ / Quintal)
                            </h3>
                            {detail.price_ref && (
                                <span className="text-[11px] text-amber-800 bg-amber-100 px-2 py-0.5 rounded">
                                    {formatBasisLabel(
                                        detail.price_ref.basis,
                                        detail.price_ref.price_date
                                    )}
                                </span>
                            )}
                        </div>

                        {detail.price_ref ? (
                            <div className="grid grid-cols-3 gap-2 pt-1 text-sm">
                                <div>
                                    <span className="text-xs text-slate-500 block">Mandi Modal</span>
                                    <span className="font-bold text-slate-900">
                                        {formatINR(detail.price_ref.modal_price)}
                                    </span>
                                </div>
                                <div>
                                    <span className="text-xs text-slate-500 block">
                                        Fair Farm-Gate (AFPP)
                                    </span>
                                    <span className="font-bold text-emerald-800">
                                        {formatINR(detail.price_ref.afpp)}
                                    </span>
                                </div>
                                <div>
                                    <span className="text-xs text-slate-500 block">Gov MSP</span>
                                    <span className="font-semibold text-slate-700">
                                        {detail.msp ? formatINR(detail.msp) : "—"}
                                    </span>
                                </div>
                            </div>
                        ) : (
                            <p className="text-xs text-slate-500 italic">
                                No mandi reference price available today.
                            </p>
                        )}

                        <p className="text-[11px] text-slate-500 pt-1 border-t border-amber-200/60">
                            MSP is shown for context, not used as a floor.
                        </p>
                    </div>

                    {/* Verification Photo Box */}
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between gap-4">
                        <div className="space-y-1">
                            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                                FPO Quality Verification
                            </h3>
                            <p className="text-xs text-slate-600">
                                Min Ask: <strong>{formatINR(detail.min_ask)}</strong> · Weighted Avg:{" "}
                                <strong>{formatINR(detail.wavg_ask)}</strong>
                            </p>
                            <p className="text-xs text-slate-500">
                                {detail.grade
                                    ? `Verified Grade ${detail.grade} at ${detail.collection_point.name}`
                                    : "Awaiting FPO field agent verification photo"}
                            </p>
                        </div>
                        {fullPhotoUrl ? (
                            <img
                                src={fullPhotoUrl}
                                alt={`Cluster C-${detail.code} sample`}
                                className="w-24 h-20 object-cover rounded-lg border border-slate-300 shrink-0"
                            />
                        ) : (
                            <div className="w-24 h-20 rounded-lg border border-dashed border-slate-300 flex items-center justify-center text-[11px] text-slate-400 text-center px-2 shrink-0">
                                No photo yet
                            </div>
                        )}
                    </div>
                </div>

                {/* Bid / Confirm / Deal Slot */}
                <div id="bid-slot" className="space-y-4">
                    {myDeal && (
                        <DealCard deal={myDeal} onStatusChange={onDealStatusChange} />
                    )}

                    {(detail.status === "CONFIRMING" || activeProgress || bidFailedInfo) && (
                        <ConfirmProgress
                            progress={
                                activeProgress || {
                                    accepted_qtl: bidFailedInfo?.accepted_qtl || 0,
                                    rejected_qtl: 0,
                                    pending_qtl: 0,
                                }
                            }
                            minQtyQtl={minQtyTarget}
                            pricePerQtl={
                                myBid?.price_per_qtl || detail.best_bid?.price_per_qtl
                            }
                            failed={Boolean(bidFailedInfo) || detail.status === "FAILED"}
                        />
                    )}

                    {!myDeal && (
                        <BidForm cluster={detail} onBidSuccess={onBidSuccess} />
                    )}
                </div>

                {/* Anonymised Farmer Lots Table */}
                <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                        Pooled Farmer Lots ({detail.lots?.length || 0})
                    </h3>
                    <div className="border border-slate-200 rounded-xl overflow-hidden">
                        <table className="w-full text-left border-collapse text-sm">
                            <thead>
                                <tr className="bg-slate-50 border-b border-slate-200 text-xs text-slate-600">
                                    <th className="py-2.5 px-4 font-semibold">Lot #</th>
                                    <th className="py-2.5 px-4 font-semibold">Quantity</th>
                                    <th className="py-2.5 px-4 font-semibold">Farmer Ask Price</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {detail.lots && detail.lots.length > 0 ? (
                                    detail.lots.map((lot) => (
                                        <tr key={lot.lot_no} className="hover:bg-slate-50/80">
                                            <td className="py-2 px-4 font-mono text-xs text-slate-600">
                                                Lot {lot.lot_no}
                                            </td>
                                            <td className="py-2 px-4 font-medium text-slate-900">
                                                {lot.qty_qtl} qtl
                                            </td>
                                            <td className="py-2 px-4 font-semibold text-emerald-700">
                                                {formatINR(lot.ask_price)}/qtl
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td
                                            colSpan={3}
                                            className="py-6 text-center text-xs text-slate-400"
                                        >
                                            No individual lot breakdown available.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
};