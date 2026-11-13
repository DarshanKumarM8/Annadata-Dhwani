// frontend/src/components/buyer/types.ts

export type ClusterStatus =
    | "OPEN"
    | "READY"
    | "BIDDING"
    | "CONFIRMING"
    | "DEAL"
    | "CLOSED"
    | "NO_BID"
    | "FAILED";

export type ClusterGrade = "A" | "B" | "C" | null;

export type PriceBasis = "DISTRICT_FRESH" | "DISTRICT_7D" | "STATE_7D";

export interface CollectionPoint {
    name: string;
    lat: number;
    lon: number;
}

export interface BestBid {
    price_per_qtl: number;
    mine: boolean;
}

export interface Cluster {
    id: string;
    code: number;
    crop_code: string;
    crop_name: string;
    district: string;
    collection_point: CollectionPoint;
    status: ClusterStatus;
    total_qtl: number;
    listing_count: number;
    min_ask: number | null;
    wavg_ask: number | null;
    grade: ClusterGrade;
    photo_url: string | null;
    bidding_ends_at: string | null;
    best_bid: BestBid | null;
    version: number;
}

export interface ClusterLot {
    lot_no: number;
    qty_qtl: number;
    ask_price: number;
}

export interface PriceRef {
    modal_price: number;
    afpp: number;
    basis: PriceBasis;
    price_date: string;
}

export interface ClusterDetailData extends Cluster {
    lots: ClusterLot[];
    price_ref: PriceRef | null;
    msp: number | null;
}

export type BidStatus =
    | "LEADING"
    | "OUTBID"
    | "CONFIRMING"
    | "DEAL"
    | "FAILED"
    | "CANCELLED";

export interface BidProgress {
    accepted_qtl: number;
    rejected_qtl: number;
    pending_qtl: number;
}

export interface MyBid {
    id: string;
    cluster_id: string;
    price_per_qtl: number;
    min_qty_qtl: number;
    status: BidStatus;
    progress?: BidProgress | null;
}

export type DealStatus =
    | "CONFIRMED"
    | "PAYMENT_REPORTED"
    | "PAID"
    | "CANCELLED";

export interface DealFpo {
    name: string;
    payee_details: string;
}

export interface MyDeal {
    id: string;
    cluster_id: string;
    qty_qtl: number;
    price_per_qtl: number;
    gross_value: number;
    platform_fee: number;
    status: DealStatus;
    pickup_by: string;
    fpo: DealFpo;
}

export function upsertCluster(list: Cluster[], incoming: Cluster): Cluster[] {
    const idx = list.findIndex((c) => c.id === incoming.id);
    if (idx === -1) {
        return [incoming, ...list];
    }
    if (incoming.version > list[idx].version) {
        const updated = [...list];
        updated[idx] = incoming;
        return updated;
    }
    return list;
}

export function assertCluster(x: unknown): x is Cluster {
    const obj = x as Record<string, any>;
    const valid =
        obj &&
        typeof obj.id === "string" &&
        typeof obj.status === "string" &&
        typeof obj.total_qtl === "number" &&
        typeof obj.version === "number" &&
        obj.collection_point &&
        typeof obj.collection_point.lat === "number" &&
        typeof obj.collection_point.lon === "number";

    if (!valid) {
        console.warn("Contract mismatch in Cluster object:", x);
    }
    return Boolean(valid);
}

export function formatINR(value: number | null | undefined): string {
    if (value === null || value === undefined) return "—";
    return "₹" + Number(value).toLocaleString("en-IN");
}