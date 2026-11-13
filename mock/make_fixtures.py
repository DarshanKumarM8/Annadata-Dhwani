"""Regenerates contracts/fixtures/*. Run from the repo root: python mock/make_fixtures.py
Owner: Darshan. Fixtures follow TASK_DIVISION.md §3 (C4, C5, C11)."""
import json
import math
import struct
import wave
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
F.mkdir(parents=True, exist_ok=True)


def w(name, obj):
    (F / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


CP = {
    "keregodu": {"name": "Keregodu FPO yard", "lat": 12.63, "lon": 76.92},
    "hosahalli": {"name": "Hosahalli point", "lat": 12.58, "lon": 76.88},
    "venue": {"name": "Venue demo point", "lat": 12.9716, "lon": 77.5946},
}
PHOTO = "/media/v/sample.svg"


def cl(i, code, crop, cname, cp, status, total, n, mn, avg, grade=None, photo=None, ends=None, best=None, v=1):
    return {
        "id": f"00000000-0000-4000-8000-0000000000{i:02d}", "code": code, "crop_code": crop, "crop_name": cname,
        "district": "Mandya", "collection_point": CP[cp], "status": status, "total_qtl": total,
        "listing_count": n, "min_ask": mn, "wavg_ask": avg, "grade": grade, "photo_url": photo,
        "bidding_ends_at": ends, "best_bid": best, "version": v,
    }


clusters = [
    cl(1, 101, "ragi", "Ragi", "keregodu", "OPEN", 17.0, 6, 3550, 3625),
    cl(2, 102, "maize", "Maize", "venue", "READY", 21.0, 7, 2050, 2120, v=4),
    cl(3, 103, "paddy_common", "Paddy", "hosahalli", "BIDDING", 26.0, 8, 2150, 2230, "B", PHOTO,
       "2026-11-13T23:30:00Z", {"price_per_qtl": 2260, "mine": False}, 9),
    cl(4, 104, "ragi", "Ragi", "hosahalli", "CONFIRMING", 24.0, 8, 3600, 3742, "A", PHOTO,
       "2026-11-13T09:00:00Z", {"price_per_qtl": 3850, "mine": True}, 12),
    cl(5, 105, "maize", "Maize", "keregodu", "DEAL", 22.0, 7, 2000, 2080, "A", PHOTO,
       "2026-11-13T07:00:00Z", {"price_per_qtl": 2150, "mine": True}, 15),
]
w("clusters.json", {"clusters": clusters})

lots = {1: [2, 3, 3, 3, 3, 3], 2: [3] * 7, 3: [3, 4, 3, 3, 3, 4, 3, 3], 4: [3] * 8, 5: [3, 3, 4, 3, 3, 3, 3]}
asks = {1: 3550, 2: 2050, 3: 2150, 4: 3600, 5: 2000}
ref = {
    "ragi": {"modal_price": 3565, "afpp": 3430, "basis": "DISTRICT_FRESH", "price_date": "2026-11-12"},
    "maize": {"modal_price": 2180, "afpp": 2070, "basis": "DISTRICT_7D", "price_date": "2026-11-10"},
    "paddy_common": {"modal_price": 2200, "afpp": 2090, "basis": "STATE_7D", "price_date": "2026-11-11"},
}
msp = {"ragi": 5205, "maize": 2410, "paddy_common": 2441}
detail = {}
for c in clusters:
    i = int(c["id"][-2:])
    detail[c["id"]] = {
        "lots": [{"lot_no": k + 1, "qty_qtl": q, "ask_price": asks[i] + 25 * k} for k, q in enumerate(lots[i])],
        "price_ref": None if i == 2 else ref[c["crop_code"]],   # cluster 102 shows the "no price" case
        "msp": msp[c["crop_code"]],
    }
w("cluster_detail.json", detail)

w("bids_mine.json", {"bids": [
    {"id": "10000000-0000-4000-8000-000000000001", "cluster_id": clusters[3]["id"], "price_per_qtl": 3850,
     "min_qty_qtl": 15, "status": "CONFIRMING",
     "progress": {"accepted_qtl": 9, "rejected_qtl": 3, "pending_qtl": 12}},
    {"id": "10000000-0000-4000-8000-000000000002", "cluster_id": clusters[4]["id"], "price_per_qtl": 2150,
     "min_qty_qtl": 15, "status": "DEAL", "progress": {"accepted_qtl": 19, "rejected_qtl": 3, "pending_qtl": 0}},
    {"id": "10000000-0000-4000-8000-000000000003", "cluster_id": clusters[2]["id"], "price_per_qtl": 2240,
     "min_qty_qtl": 20, "status": "OUTBID", "progress": None},
]})

FPO = {"name": "Keregodu Farmer Producer Company", "payee_details": "UPI keregodu-fpo@bank (demo)"}
w("deals_mine.json", {"deals": [
    {"id": "20000000-0000-4000-8000-000000000001", "cluster_id": clusters[4]["id"], "qty_qtl": 19,
     "price_per_qtl": 2150, "gross_value": 40850, "platform_fee": 612.75, "status": "CONFIRMED",
     "pickup_by": "2026-11-16", "fpo": FPO},
]})

w("agent_tasks.json", {
    "verify": [clusters[1]],
    "tickets": [
        {"id": "30000000-0000-4000-8000-000000000001", "village": "Keregodu", "first_name": "Ramesh",
         "reason": "IVR_FAIL_3", "status": "OPEN", "created_at": "2026-11-13T06:10:00Z"},
        {"id": "30000000-0000-4000-8000-000000000002", "village": "Hosahalli", "first_name": "Lakshmi",
         "reason": "HELP_KEY", "status": "ASSIGNED", "created_at": "2026-11-13T06:40:00Z"},
    ],
    "deals": [{"id": "20000000-0000-4000-8000-000000000001", "cluster_code": 105, "status": "PAYMENT_REPORTED",
               "qty_qtl": 19, "gross_value": 40850}],
})

w("ops_calls.json", {
    "sessions": [
        {"phone_masked": "+91•••••0001", "kind": "LISTING", "state": "PRICE", "provider": "sim", "version": 7,
         "updated_at": "2026-11-13T07:01:10Z"},
        {"phone_masked": "+91•••••0007", "kind": "BID_OFFER", "state": "OFFER", "provider": "exotel", "version": 2,
         "updated_at": "2026-11-13T07:01:12Z"},
    ],
    "jobs": [
        {"id": "40000000-0000-4000-8000-000000000001", "kind": "BID_OFFER", "status": "IN_CALL", "attempts": 1,
         "run_at": "2026-11-13T07:00:50Z"},
        {"id": "40000000-0000-4000-8000-000000000002", "kind": "BID_OFFER", "status": "QUEUED", "attempts": 0,
         "run_at": "2026-11-13T07:01:20Z"},
        {"id": "40000000-0000-4000-8000-000000000003", "kind": "CALLBACK", "status": "DONE", "attempts": 1,
         "run_at": "2026-11-13T06:58:00Z"},
    ],
    "breaker": {"calls_today": 14, "budget": 200},
})

S1, S2 = "50000000-0000-4000-8000-000000000001", "50000000-0000-4000-8000-000000000002"
w("ops_dtmf.json", {"events": [
    {"session_id": S1, "state_before": "QTY", "digits": "3", "state_after": "QTY_CONFIRM", "dropped_reason": None,
     "at": "2026-11-13T07:00:41Z"},
    {"session_id": S1, "state_before": "QTY", "digits": "3", "state_after": "QTY", "dropped_reason": "BOUNCE",
     "at": "2026-11-13T07:00:40Z"},
    {"session_id": S1, "state_before": "CROP", "digits": "1", "state_after": "QTY", "dropped_reason": None,
     "at": "2026-11-13T07:00:30Z"},
    {"session_id": S2, "state_before": "PRICE", "digits": "38000", "state_after": "PRICE",
     "dropped_reason": "OUT_OF_RANGE", "at": "2026-11-13T06:59:02Z"},
]})

w("health.json", {"db": "ok", "redis": "ok", "tts_clips": 216, "price_age_days": 0, "provider": "sim",
                  "public_base_url_ok": True})

# Scripted dashboard story (C5). The mock assigns seq numbers and loops it.
c1 = clusters[0]


def upd(**k):
    d = dict(c1)
    d.update(k)
    return d


B = dict(total_qtl=20.0, listing_count=7, wavg_ask=3597, min_ask=3430)
V = dict(grade="A", photo_url=PHOTO, bidding_ends_at="2026-11-13T23:59:00Z")
BID1, BID2 = "10000000-0000-4000-8000-000000000010", "10000000-0000-4000-8000-000000000011"
story = [
    {"type": "listing.created", "audience": "all",
     "payload": {"cluster_id": c1["id"], "crop_code": "ragi", "qty_qtl": 3, "ask_price": 3430, "source": "IVR"}},
    {"type": "cluster.updated", "audience": "all", "payload": upd(**B, status="READY", version=2)},
    {"type": "task.created", "audience": "agent", "payload": {"kind": "VERIFY", "ref_id": c1["id"]}},
    {"type": "cluster.updated", "audience": "all", "payload": upd(**B, **V, status="BIDDING", version=3)},
    {"type": "bid.placed", "audience": "buyer",
     "payload": {"cluster_id": c1["id"], "bid_id": BID1, "price_per_qtl": 3600, "buyer_is_you": False}},
    {"type": "cluster.updated", "audience": "all",
     "payload": upd(**B, **V, status="BIDDING", best_bid={"price_per_qtl": 3600, "mine": False}, version=4)},
    {"type": "bid.placed", "audience": "buyer",
     "payload": {"cluster_id": c1["id"], "bid_id": BID2, "price_per_qtl": 3650, "buyer_is_you": True}},
    {"type": "cluster.updated", "audience": "all",
     "payload": upd(**B, **V, status="CONFIRMING", best_bid={"price_per_qtl": 3650, "mine": True}, version=5)},
    {"type": "bid.confirming", "audience": "buyer",
     "payload": {"cluster_id": c1["id"], "bid_id": BID2, "accepted_qtl": 3, "rejected_qtl": 0, "pending_qtl": 17}},
    {"type": "bid.confirming", "audience": "buyer",
     "payload": {"cluster_id": c1["id"], "bid_id": BID2, "accepted_qtl": 9, "rejected_qtl": 3, "pending_qtl": 8}},
    {"type": "bid.confirming", "audience": "buyer",
     "payload": {"cluster_id": c1["id"], "bid_id": BID2, "accepted_qtl": 17, "rejected_qtl": 3, "pending_qtl": 0}},
    {"type": "deal.created", "audience": "buyer",
     "payload": {"deal_id": "20000000-0000-4000-8000-000000000010", "cluster_id": c1["id"], "qty_qtl": 17,
                 "price_per_qtl": 3650, "gross_value": 62050, "platform_fee": 930.75, "pickup_by": "2026-11-16"}},
    {"type": "cluster.updated", "audience": "all",
     "payload": upd(**B, **V, status="DEAL", best_bid={"price_per_qtl": 3650, "mine": True}, version=6)},
]
w("events_story.json", story)

# Placeholder prompt: 1.2 s two-tone beep, 8 kHz mono 16-bit PCM (same format as real clips).
sr = 8000
frames = bytearray()
for n in range(int(sr * 1.2)):
    t = n / sr
    s = 0.3 * (math.sin(2 * math.pi * 440 * t) + math.sin(2 * math.pi * 660 * t)) / 2 if (t % 0.4) < 0.25 else 0.0
    frames += struct.pack("<h", int(s * 32767))
with wave.open(str(F / "sample.wav"), "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(bytes(frames))

(F / "sample.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420">'
    '<rect width="640" height="420" fill="#c8a165"/>'
    '<text x="320" y="215" font-size="32" text-anchor="middle" fill="#3b2a12" font-family="sans-serif">'
    'Sample grain photo (mock)</text></svg>\n', encoding="utf-8")

print("fixtures:", sorted(p.name for p in F.iterdir()))
