// frontend/src/components/buyer/ClusterMap.tsx
import React, { useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { Cluster, ClusterStatus, formatINR } from "./types";

interface ClusterMapProps {
    clusters: Cluster[];
    selectedId?: string;
    onSelect: (id: string) => void;
}

const MARKER_COLORS: Record<ClusterStatus, { stroke: string; fill: string }> = {
    OPEN: { stroke: "#475569", fill: "#94a3b8" },       // slate
    READY: { stroke: "#b45309", fill: "#f59e0b" },      // amber
    BIDDING: { stroke: "#047857", fill: "#10b981" },    // emerald
    CONFIRMING: { stroke: "#1d4ed8", fill: "#3b82f6" }, // blue
    DEAL: { stroke: "#6d28d9", fill: "#8b5cf6" },       // purple
    CLOSED: { stroke: "#4b5563", fill: "#9ca3af" },     // gray
    NO_BID: { stroke: "#b91c1c", fill: "#ef4444" },     // red
    FAILED: { stroke: "#991b1b", fill: "#f87171" },     // red
};

function computeRadius(totalQtl: number): number {
    // Scale radius by total_qtl (min 6, max 20)
    const scaled = 6 + (totalQtl / 50) * 14;
    return Math.max(6, Math.min(20, Math.round(scaled)));
}

export const ClusterMap: React.FC<ClusterMapProps> = ({
    clusters,
    selectedId,
    onSelect,
}) => {
    const [tileError, setTileError] = useState<boolean>(false);

    if (tileError) {
        return (
            <div className="bg-white rounded-xl border border-slate-200 px-4 py-2.5 text-xs text-slate-500 flex items-center justify-between">
                <span>Map unavailable</span>
                <span className="text-[11px] text-slate-400">
                    List view remains active
                </span>
            </div>
        );
    }

    // Center on Mandya/Mysuru default or first cluster's collection point
    const defaultCenter: [number, number] =
        clusters.length > 0
            ? [clusters[0].collection_point.lat, clusters[0].collection_point.lon]
            : [12.56, 76.85];

    return (
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden h-52 relative z-0 shrink-0">
            <MapContainer
                center={defaultCenter}
                zoom={10}
                scrollWheelZoom={false}
                className="h-full w-full"
            >
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                    eventHandlers={{
                        tileerror: () => setTileError(true),
                    }}
                />

                {clusters.map((c) => {
                    const isSelected = c.id === selectedId;
                    const colors = MARKER_COLORS[c.status] || MARKER_COLORS.OPEN;
                    const radius = computeRadius(c.total_qtl);

                    return (
                        <CircleMarker
                            key={c.id}
                            center={[c.collection_point.lat, c.collection_point.lon]}
                            radius={isSelected ? radius + 3 : radius}
                            pathOptions={{
                                color: isSelected ? "#064e3b" : colors.stroke,
                                weight: isSelected ? 3 : 2,
                                fillColor: colors.fill,
                                fillOpacity: isSelected ? 0.9 : 0.7,
                            }}
                            eventHandlers={{
                                click: () => onSelect(c.id),
                            }}
                        >
                            <Tooltip direction="top" offset={[0, -6]} opacity={0.95}>
                                <div className="text-xs">
                                    <div className="font-bold">
                                        C-{c.code} · {c.crop_name} ({c.status})
                                    </div>
                                    <div>
                                        {c.collection_point.name} ·{" "}
                                        <strong>{(c.total_qtl / 10).toFixed(1)} t</strong> (
                                        {c.total_qtl} qtl)
                                    </div>
                                    {c.best_bid && (
                                        <div className="text-emerald-700 font-semibold">
                                            Best bid: {formatINR(c.best_bid.price_per_qtl)}/qtl
                                        </div>
                                    )}
                                </div>
                            </Tooltip>
                        </CircleMarker>
                    );
                })}
            </MapContainer>
        </div>
    );
};