// frontend/src/components/buyer/BidForm.tsx
import React, { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { type ClusterDetailData, formatINR, type MyBid } from "./types";

interface BidFormProps {
    cluster: ClusterDetailData;
    onBidSuccess: (bid: MyBid) => void;
}

export const BidForm: React.FC<BidFormProps> = ({ cluster, onBidSuccess }) => {
    const defaultPrice = cluster.best_bid
        ? cluster.best_bid.price_per_qtl + 10
        : cluster.min_ask || 3500;

    const [price, setPrice] = useState<string>(String(defaultPrice));
    const [minQty, setMinQty] = useState<string>(String(cluster.total_qtl));
    const [sending, setSending] = useState<boolean>(false);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const [successMsg, setSuccessMsg] = useState<string | null>(null);

    // Reuse the same Idempotency-Key if a network error occurs and the user retries;
    // clear it so a fresh UUID is generated after any server response.
    const idempotencyKeyRef = useRef<string | null>(null);

    useEffect(() => {
        const nextDefault = cluster.best_bid
            ? cluster.best_bid.price_per_qtl + 10
            : cluster.min_ask || 3500;
        setPrice(String(nextDefault));
        setMinQty(String(cluster.total_qtl));
        setErrorMsg(null);
        setSuccessMsg(null);
        idempotencyKeyRef.current = null;
    }, [cluster.id, cluster.best_bid?.price_per_qtl, cluster.min_ask, cluster.total_qtl]);

    const isBidding = cluster.status === "BIDDING";
    const numericPrice = Number(price) || 0;
    const numericMinQty = Number(minQty) || 0;

    // Compute how many quintals have ask_price <= numericPrice
    const coveredQtl = (cluster.lots || [])
        .filter((l) => l.ask_price <= numericPrice)
        .reduce((acc, l) => acc + l.qty_qtl, 0);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!isBidding || sending) return;

        setSending(true);
        setErrorMsg(null);
        setSuccessMsg(null);

        if (!idempotencyKeyRef.current) {
            idempotencyKeyRef.current = crypto.randomUUID();
        }
        const keyToUse = idempotencyKeyRef.current;

        try {
            const res = await api.post(
                `/api/clusters/${cluster.id}/bids`,
                {
                    price_per_qtl: numericPrice,
                    min_qty_qtl: numericMinQty,
                },
                { "Idempotency-Key": keyToUse }
            );

            // Server responded -> reset key for the next new bid attempt
            idempotencyKeyRef.current = null;

            setSuccessMsg(
                `Bid placed: ${formatINR(res.price_per_qtl)}/qtl (min ${res.min_qty_qtl} qtl)`
            );
            onBidSuccess({
                id: res.id,
                cluster_id: cluster.id,
                price_per_qtl: res.price_per_qtl,
                min_qty_qtl: res.min_qty_qtl,
                status: res.status || "LEADING",
                progress: null,
            });
        } catch (err: any) {
            // If err.status is present, the server responded (409/422/etc.), so reset the key
            if (err && typeof err.status === "number") {
                idempotencyKeyRef.current = null;
                const code = err.body?.error;
                if (code === "BID_TOO_LOW") {
                    const minNext = err.body?.min_next;
                    setErrorMsg(
                        minNext
                            ? `Bid at least ${formatINR(minNext)}`
                            : "Your bid is too low. Please bid at least ₹10 above the current best bid."
                    );
                    if (minNext) setPrice(String(minNext));
                } else if (code === "CLUSTER_NOT_BIDDING") {
                    setErrorMsg("This cluster is not open for bidding right now.");
                } else if (code === "MIN_QTY_TOO_HIGH") {
                    setErrorMsg(
                        `Minimum quantity cannot exceed the cluster total of ${cluster.total_qtl} quintals.`
                    );
                } else {
                    setErrorMsg(err.body?.error || "Could not place bid.");
                }
            } else {
                // Network error with no server response: keep idempotencyKeyRef.current for retry
                setErrorMsg(
                    "Network error while sending bid. Click Place bid again to safely retry."
                );
            }
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/40 space-y-3">
            <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-900">
                    Place Wholesale Bid
                </h3>
                {!isBidding && (
                    <span className="text-xs text-slate-500 italic">
                        Bidding is only enabled when status is BIDDING (current:{" "}
                        {cluster.status})
                    </span>
                )}
            </div>

            <form
                onSubmit={handleSubmit}
                className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end"
            >
                <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                        Bid Price (₹ / quintal)
                    </label>
                    <input
                        type="number"
                        min={1}
                        step={1}
                        disabled={!isBidding || sending}
                        value={price}
                        onChange={(e) => setPrice(e.target.value)}
                        className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white text-slate-900 disabled:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-600"
                        required
                    />
                </div>

                <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                        Minimum Quantity (max {cluster.total_qtl} qtl)
                    </label>
                    <input
                        type="number"
                        min={1}
                        max={cluster.total_qtl}
                        step="0.5"
                        disabled={!isBidding || sending}
                        value={minQty}
                        onChange={(e) => setMinQty(e.target.value)}
                        className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white text-slate-900 disabled:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-600"
                        required
                    />
                </div>

                <button
                    type="submit"
                    disabled={!isBidding || sending}
                    className="w-full text-sm font-semibold bg-emerald-700 hover:bg-emerald-800 disabled:bg-slate-300 disabled:text-slate-500 text-white py-2 px-4 rounded-lg transition cursor-pointer disabled:cursor-not-allowed"
                >
                    {sending ? "Sending bid..." : "Place bid"}
                </button>
            </form>

            <div className="text-xs text-slate-600">
                At <strong>{formatINR(numericPrice)}</strong>,{" "}
                <strong>{coveredQtl}</strong> of{" "}
                <strong>{cluster.total_qtl}</strong> quintals have an asking price at or
                below your bid.
            </div>

            {errorMsg && (
                <div className="text-xs font-medium text-red-700 bg-red-100 border border-red-200 rounded-lg px-3 py-2">
                    {errorMsg}
                </div>
            )}

            {successMsg && (
                <div className="text-xs font-medium text-emerald-800 bg-emerald-100 border border-emerald-300 rounded-lg px-3 py-2">
                    {successMsg}
                </div>
            )}
        </div>
    );
};