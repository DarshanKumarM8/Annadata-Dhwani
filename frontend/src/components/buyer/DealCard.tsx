// frontend/src/components/buyer/DealCard.tsx
import React, { useState } from "react";
import { api } from "../../lib/api";
import { type DealStatus, formatINR, type MyDeal } from "./types";

interface DealCardProps {
    deal: MyDeal;
    onStatusChange: (dealId: string, newStatus: DealStatus) => void;
}

const STEPS: DealStatus[] = ["CONFIRMED", "PAYMENT_REPORTED", "PAID"];

export const DealCard: React.FC<DealCardProps> = ({ deal, onStatusChange }) => {
    const [paymentRef, setPaymentRef] = useState<string>("");
    const [submitting, setSubmitting] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const currentIdx = STEPS.indexOf(deal.status);

    const handleReportPayment = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!paymentRef.trim() || submitting) return;

        try {
            setSubmitting(true);
            setError(null);
            const res = await api.post(`/api/deals/${deal.id}/payment-reported`, {
                payment_ref: paymentRef.trim(),
            });
            onStatusChange(deal.id, res.status || "PAYMENT_REPORTED");
        } catch (err: any) {
            setError(err?.body?.error || err?.message || "Failed to report payment");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="p-5 rounded-xl border-2 border-purple-300 bg-purple-50/40 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-purple-900">
                        Deal Closed · Settlement Handoff
                    </span>
                    <h3 className="text-lg font-extrabold text-slate-900 mt-0.5">
                        {deal.qty_qtl} qtl @ {formatINR(deal.price_per_qtl)}/qtl
                    </h3>
                </div>

                <span className="text-xs font-bold px-3 py-1 rounded-full bg-purple-700 text-white">
                    {deal.status}
                </span>
            </div>

            {/* Status Timeline: CONFIRMED -> PAYMENT_REPORTED -> PAID */}
            <div className="grid grid-cols-3 gap-2 pt-1">
                {STEPS.map((step, idx) => {
                    const active = idx <= currentIdx;
                    return (
                        <div
                            key={step}
                            className={`text-center py-1.5 px-2 rounded-lg text-xs font-semibold border ${active
                                    ? "bg-emerald-700 text-white border-emerald-700"
                                    : "bg-white text-slate-400 border-slate-200"
                                }`}
                        >
                            {idx + 1}. {step.replace("_", " ")}
                        </div>
                    );
                })}
            </div>

            {/* Financials & FPO Payee Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-white p-3.5 rounded-xl border border-purple-200 text-xs">
                <div>
                    <span className="text-slate-500 block">Gross Crop Value</span>
                    <span className="text-base font-extrabold text-slate-900">
                        {formatINR(deal.gross_value)}
                    </span>
                    <span className="text-slate-500 block mt-0.5">
                        Pickup by: <strong>{deal.pickup_by}</strong>
                    </span>
                </div>

                <div>
                    <span className="text-slate-500 block">Platform Facilitation Fee</span>
                    <span className="text-sm font-bold text-slate-800">
                        {formatINR(deal.platform_fee)}
                    </span>
                    <span className="text-[11px] text-slate-500 block mt-0.5">
                        1.5% fee, invoiced to you
                    </span>
                </div>

                <div>
                    <span className="text-slate-500 block">Seller of Record (FPO)</span>
                    <span className="font-bold text-slate-900 block">
                        {deal.fpo?.name || "Partner FPO"}
                    </span>
                    <span className="font-mono text-emerald-800 bg-emerald-50 px-1.5 py-0.5 rounded inline-block mt-0.5">
                        {deal.fpo?.payee_details || "UPI on invoice"}
                    </span>
                </div>
            </div>

            <p className="text-xs font-medium text-amber-900 bg-amber-100/80 border border-amber-300 rounded-lg px-3 py-2">
                Pay the FPO directly. Loading only after the FPO confirms payment.
            </p>

            {/* Report UTR Form when status is CONFIRMED */}
            {deal.status === "CONFIRMED" && (
                <form
                    onSubmit={handleReportPayment}
                    className="flex flex-wrap items-center gap-2 pt-1"
                >
                    <input
                        type="text"
                        placeholder="Enter bank UTR / UPI Reference (e.g. UTR123456)"
                        value={paymentRef}
                        onChange={(e) => setPaymentRef(e.target.value)}
                        className="flex-1 min-w-[220px] text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-600"
                        required
                    />
                    <button
                        type="submit"
                        disabled={submitting}
                        className="text-sm font-semibold bg-purple-700 hover:bg-purple-800 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg transition cursor-pointer"
                    >
                        {submitting ? "Reporting..." : "Report Payment Sent"}
                    </button>
                </form>
            )}

            {error && (
                <div className="text-xs text-red-600 font-medium">{error}</div>
            )}
        </div>
    );
};