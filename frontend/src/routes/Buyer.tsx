// frontend/src/routes/Buyer.tsx
import React, { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useEvents, type WsEvent } from "../lib/ws";
import { ClusterList } from "../components/buyer/ClusterList";
import { ClusterDetail } from "../components/buyer/ClusterDetail";
import { ClusterMap } from "../components/buyer/ClusterMap";
import {
  type BidProgress,
  type Cluster,
  type ClusterDetailData,
  type ClusterStatus,
  type DealStatus,
  type MyBid,
  type MyDeal,
  assertCluster,
  upsertCluster,
} from "../components/buyer/types";

const DEFAULT_STATUSES: ClusterStatus[] = [
  "OPEN",
  "READY",
  "BIDDING",
  "CONFIRMING",
  "DEAL",
];

export const Buyer: React.FC = () => {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);
  const [detail, setDetail] = useState<ClusterDetailData | null>(null);

  const [myBids, setMyBids] = useState<Record<string, MyBid>>({});
  const [myDeals, setMyDeals] = useState<Record<string, MyDeal>>({});
  const [liveProgressByCluster, setLiveProgressByCluster] = useState<
    Record<string, BidProgress>
  >({});
  const [bidFailedByCluster, setBidFailedByCluster] = useState<
    Record<string, { accepted_qtl: number; min_qty_qtl: number }>
  >({});

  const [listLoading, setListLoading] = useState<boolean>(true);
  const [listError, setListError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [selectedStatuses, setSelectedStatuses] =
    useState<ClusterStatus[]>(DEFAULT_STATUSES);
  const [selectedCrop, setSelectedCrop] = useState<string>("");

  const fetchClusters = useCallback(async () => {
    try {
      setListError(null);
      const res = await api.get(
        "/api/clusters?status=OPEN,READY,BIDDING,CONFIRMING,DEAL"
      );
      const items: Cluster[] = res.clusters || [];
      items.forEach(assertCluster);
      setClusters(items);
      setSelectedId((prev) =>
        prev ?? (items.length > 0 ? items[0].id : undefined)
      );
    } catch (err: any) {
      setListError(
        err?.body?.error || err?.message || "Failed to load clusters"
      );
    } finally {
      setListLoading(false);
    }
  }, []);

  const fetchBidsAndDeals = useCallback(async () => {
    try {
      const [bidsRes, dealsRes] = await Promise.all([
        api.get("/api/bids/mine"),
        api.get("/api/deals/mine"),
      ]);
      const bidsMap: Record<string, MyBid> = {};
      (bidsRes.bids || []).forEach((b: MyBid) => {
        bidsMap[b.cluster_id] = b;
      });
      setMyBids(bidsMap);

      const dealsMap: Record<string, MyDeal> = {};
      (dealsRes.deals || []).forEach((d: MyDeal) => {
        dealsMap[d.cluster_id] = d;
      });
      setMyDeals(dealsMap);
    } catch (err) {
      console.warn("Could not load /api/bids/mine or /api/deals/mine:", err);
    }
  }, []);

  const fetchClusterDetail = useCallback(async (id: string) => {
    try {
      setDetailLoading(true);
      setDetailError(null);
      const res: ClusterDetailData = await api.get(`/api/clusters/${id}`);
      setDetail(res);
    } catch (err: any) {
      setDetailError(
        err?.body?.error || err?.message || "Failed to load cluster detail"
      );
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchClusters();
    fetchBidsAndDeals();
  }, [fetchClusters, fetchBidsAndDeals]);

  useEffect(() => {
    if (selectedId) {
      fetchClusterDetail(selectedId);
    }
  }, [selectedId, fetchClusterDetail]);

  const handleWsEvent = useCallback(
    (ev: WsEvent) => {
      const p = ev.payload;
      if (!p) return;

      switch (ev.type) {
        case "cluster.updated": {
          const incoming: Cluster = p;
          assertCluster(incoming);
          setClusters((prev) => upsertCluster(prev, incoming));
          setDetail((prev) =>
            prev && prev.id === incoming.id && incoming.version > prev.version
              ? { ...prev, ...incoming }
              : prev
          );
          break;
        }
        case "listing.created": {
          if (selectedId && p.cluster_id === selectedId) {
            fetchClusterDetail(selectedId);
          }
          break;
        }
        case "bid.placed": {
          const { cluster_id, price_per_qtl, buyer_is_you } = p;
          setClusters((prev) =>
            prev.map((c) =>
              c.id === cluster_id
                ? {
                  ...c,
                  best_bid: { price_per_qtl, mine: Boolean(buyer_is_you) },
                }
                : c
            )
          );
          setDetail((prev) =>
            prev && prev.id === cluster_id
              ? {
                ...prev,
                best_bid: { price_per_qtl, mine: Boolean(buyer_is_you) },
              }
              : prev
          );
          break;
        }
        case "bid.confirming": {
          const { cluster_id, accepted_qtl, rejected_qtl, pending_qtl } = p;
          setLiveProgressByCluster((prev) => ({
            ...prev,
            [cluster_id]: { accepted_qtl, rejected_qtl, pending_qtl },
          }));
          setClusters((prev) =>
            prev.map((c) =>
              c.id === cluster_id ? { ...c, status: "CONFIRMING" } : c
            )
          );
          setDetail((prev) =>
            prev && prev.id === cluster_id
              ? { ...prev, status: "CONFIRMING" }
              : prev
          );
          break;
        }
        case "bid.failed": {
          const { cluster_id, accepted_qtl, min_qty_qtl } = p;
          setBidFailedByCluster((prev) => ({
            ...prev,
            [cluster_id]: { accepted_qtl, min_qty_qtl },
          }));
          break;
        }
        case "deal.created": {
          const newDeal: MyDeal = {
            id: p.deal_id,
            cluster_id: p.cluster_id,
            qty_qtl: p.qty_qtl,
            price_per_qtl: p.price_per_qtl,
            gross_value: p.gross_value,
            platform_fee: p.platform_fee,
            status: "CONFIRMED",
            pickup_by: p.pickup_by,
            fpo: p.fpo || {
              name: "Keregodu FPO",
              payee_details: "UPI keregodu-fpo@bank",
            },
          };
          setMyDeals((prev) => ({ ...prev, [p.cluster_id]: newDeal }));
          setClusters((prev) =>
            prev.map((c) =>
              c.id === p.cluster_id ? { ...c, status: "DEAL" } : c
            )
          );
          setDetail((prev) =>
            prev && prev.id === p.cluster_id ? { ...prev, status: "DEAL" } : prev
          );
          fetchBidsAndDeals();
          break;
        }
        case "deal.updated": {
          const { deal_id, status } = p;
          setMyDeals((prev) => {
            const next = { ...prev };
            Object.keys(next).forEach((cid) => {
              if (next[cid].id === deal_id) {
                next[cid] = { ...next[cid], status };
              }
            });
            return next;
          });
          break;
        }
      }
    },
    [selectedId, fetchClusterDetail, fetchBidsAndDeals]
  );

  const handleResync = useCallback(() => {
    fetchClusters();
    fetchBidsAndDeals();
    if (selectedId) {
      fetchClusterDetail(selectedId);
    }
  }, [fetchClusters, fetchBidsAndDeals, fetchClusterDetail, selectedId]);

  const { connected } = useEvents(handleWsEvent, handleResync);

  const handleToggleStatus = (status: ClusterStatus) => {
    setSelectedStatuses((prev) =>
      prev.includes(status)
        ? prev.filter((s) => s !== status)
        : [...prev, status]
    );
  };

  const handleBidSuccess = (bid: MyBid) => {
    setMyBids((prev) => ({ ...prev, [bid.cluster_id]: bid }));
    setClusters((prev) =>
      prev.map((c) =>
        c.id === bid.cluster_id
          ? { ...c, best_bid: { price_per_qtl: bid.price_per_qtl, mine: true } }
          : c
      )
    );
    setDetail((prev) =>
      prev && prev.id === bid.cluster_id
        ? {
          ...prev,
          best_bid: { price_per_qtl: bid.price_per_qtl, mine: true },
        }
        : prev
    );
  };

  const handleDealStatusChange = (dealId: string, newStatus: DealStatus) => {
    setMyDeals((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((cid) => {
        if (next[cid].id === dealId) {
          next[cid] = { ...next[cid], status: newStatus };
        }
      });
      return next;
    });
  };

  const filteredForMap = clusters.filter((c) => {
    const statusOk =
      selectedStatuses.length === 0 || selectedStatuses.includes(c.status);
    const cropOk = !selectedCrop || c.crop_code === selectedCrop;
    return statusOk && cropOk;
  });

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      {/* Top Navbar */}
      <header className="bg-emerald-900 text-white px-6 py-3.5 shadow-xs flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-extrabold tracking-tight">
            अन्नदाता ध्वनि · Annadata Dhwani
          </span>
          <span className="text-xs bg-emerald-800 text-emerald-100 px-2.5 py-0.5 rounded-full font-medium">
            Wholesale Buyer Marketplace
          </span>
          <span className="text-[11px] bg-amber-400/20 text-amber-200 border border-amber-400/40 px-2 py-0.5 rounded font-mono">
            Demo data
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs bg-emerald-950/60 px-2.5 py-1 rounded-full border border-emerald-800">
            <span
              className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-red-500"
                }`}
            />
            <span className="text-emerald-100">
              {connected ? "Live WS" : "Reconnecting..."}
            </span>
          </div>

          <button
            type="button"
            onClick={handleResync}
            className="text-xs bg-emerald-800 hover:bg-emerald-700 px-3 py-1.5 rounded-lg border border-emerald-700 transition cursor-pointer"
          >
            ↻ Refresh
          </button>
        </div>
      </header>

      {/* Main 2-Column Content (1280px desktop layout) */}
      <main className="flex-1 max-w-[1400px] w-full mx-auto p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column: Map + Cluster List (5 cols) */}
        <div className="lg:col-span-5 flex flex-col gap-3 h-[calc(100vh-88px)]">
          <ClusterMap
            clusters={filteredForMap}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />

          <div className="flex-1 min-h-0">
            {listLoading ? (
              <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-sm text-slate-500 h-full flex items-center justify-center">
                Loading clusters...
              </div>
            ) : listError ? (
              <div className="bg-white rounded-xl border border-red-200 p-6 text-center text-sm text-red-600 h-full flex items-center justify-center">
                {listError}
              </div>
            ) : (
              <ClusterList
                clusters={clusters}
                selectedId={selectedId}
                onSelect={setSelectedId}
                selectedStatuses={selectedStatuses}
                onToggleStatus={handleToggleStatus}
                selectedCrop={selectedCrop}
                onCropChange={setSelectedCrop}
              />
            )}
          </div>
        </div>

        {/* Right Column: Cluster Detail (7 cols) */}
        <div className="lg:col-span-7 flex flex-col h-[calc(100vh-88px)]">
          <ClusterDetail
            detail={detail}
            loading={detailLoading}
            error={detailError}
            myBid={selectedId ? myBids[selectedId] : null}
            myDeal={selectedId ? myDeals[selectedId] : null}
            liveProgress={selectedId ? liveProgressByCluster[selectedId] : null}
            bidFailedInfo={selectedId ? bidFailedByCluster[selectedId] : null}
            onBidSuccess={handleBidSuccess}
            onDealStatusChange={handleDealStatusChange}
          />
        </div>
      </main>
    </div>
  );
};

export default Buyer;