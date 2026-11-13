"""D5 end-to-end: verify -> bid -> outbid -> confirm round (timeout fails, then farmers accept) -> deal -> payment.
Real Postgres + Valkey (skipped if they are not up)."""
import asyncio
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app import cache, db
from app.api.auth import ApiError
from app.config import settings
from app.services import bidding, clustering
from test_d4 import CP, PASSWORD, PREFIX, session, setup_farmers, teardown
from test_reliability import STACK_UP

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


async def teardown5() -> None:
    c = await asyncpg.connect(settings.database_url)
    cl = "(SELECT id FROM clusters WHERE collection_point_id = $1::uuid)"
    await c.execute(f"UPDATE clusters SET best_bid_id = NULL WHERE collection_point_id = $1::uuid", CP)
    await c.execute(f"DELETE FROM deals WHERE cluster_id IN {cl}", CP)
    await c.execute(f"DELETE FROM bid_responses WHERE bid_id IN (SELECT id FROM bids WHERE cluster_id IN {cl})", CP)
    await c.execute(f"DELETE FROM bids WHERE cluster_id IN {cl}", CP)
    await c.execute(f"DELETE FROM verifications WHERE cluster_id IN {cl}", CP)
    await c.close()
    await teardown()


@pytest.fixture
def clean5():
    asyncio.run(teardown5())
    yield
    asyncio.run(teardown5())


def login(client, email):
    r = client.post("/api/auth/buyer/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["buyer"]["id"]


def hdr(tok, key=None):
    return {"Authorization": f"Bearer {tok}", **({"Idempotency-Key": key} if key else {})}


def photo():
    return {"photo": ("s.jpg", io.BytesIO(b"\xff\xd8\xff fake jpeg"), "image/jpeg")}


def vform(lat=12.55, lon=76.95, minutes_old=0, grade="A"):
    cap = datetime.now(timezone.utc) - timedelta(minutes=minutes_old)
    return {"grade": grade, "lat": lat, "lon": lon, "accuracy_m": 12, "captured_at": cap.isoformat()}


def test_full_trade_flow(clean5):
    from fastapi.testclient import TestClient
    from app.main import app

    farmers = asyncio.run(setup_farmers(5))
    with TestClient(app) as client:
        for i, (p, f) in enumerate(farmers):
            client.portal.call(clustering.commit_listing, db.pool, session(p, f, 5, 3000 + 10 * i))
        t1, b1 = login(client, "buyer1@demo.test")
        t2, b2 = login(client, "buyer2@demo.test")
        ta, _ = login(client, "admin@demo.test")
        cid = next(c["id"] for c in client.get("/api/clusters?status=READY", headers=hdr(t1)).json()["clusters"]
                   if c["collection_point"]["name"] == "D4 test yard")

        # --- agent verification ---
        ag = client.post("/api/auth/agent/login", json={"phone": "+919800000099", "pin": "1234"})
        assert ag.status_code == 200
        tag = ag.json()["token"]
        assert client.post("/api/auth/agent/login", json={"phone": "+919800000099", "pin": "0000"}).status_code == 401
        assert cid in [c["id"] for c in client.get("/api/agent/tasks", headers=hdr(tag)).json()["verify"]]
        assert client.get("/api/agent/tasks", headers=hdr(t1)).status_code == 403          # buyer is not an agent
        v = f"/api/agent/clusters/{cid}/verification"
        far = client.post(v, headers=hdr(tag), data=vform(lat=12.80), files=photo())
        assert far.status_code == 422 and far.json()["error"] == "TOO_FAR" and far.json()["distance_m"] > 500
        assert client.post(v, headers=hdr(tag), data=vform(minutes_old=15), files=photo()).json()["error"] == "STALE_CAPTURE"
        assert client.post(f"/api/clusters/{cid}/bids", headers=hdr(t1, "early"),
                           json={"price_per_qtl": 4000, "min_qty_qtl": 10}).json()["error"] == "CLUSTER_NOT_BIDDING"
        ok = client.post(v, headers=hdr(tag), data=vform(), files=photo())
        assert ok.status_code == 201 and ok.json()["status"] == "BIDDING" and ok.json()["bidding_ends_at"]
        assert client.post(v, headers=hdr(tag), data=vform(), files=photo()).json()["error"] == "ALREADY_VERIFIED"

        # --- bidding ---
        url = f"/api/clusters/{cid}/bids"
        low = client.post(url, headers=hdr(t1, "k0"), json={"price_per_qtl": 2900, "min_qty_qtl": 10})
        assert low.status_code == 409 and low.json() == {"error": "BID_TOO_LOW", "min_next": 3000.0}
        assert client.post(url, headers=hdr(t1, "k0"), json={"price_per_qtl": 3100, "min_qty_qtl": 99}
                           ).json()["error"] == "MIN_QTY_TOO_HIGH"
        first = client.post(url, headers=hdr(t1, "k1"), json={"price_per_qtl": 3100, "min_qty_qtl": 20})
        assert first.status_code == 201 and first.json()["status"] == "LEADING"
        again = client.post(url, headers=hdr(t1, "k1"), json={"price_per_qtl": 3100, "min_qty_qtl": 20})
        assert again.status_code == 200 and again.json()["id"] == first.json()["id"]          # double click = one bid
        assert client.post(url, headers=hdr(t2, "k2"), json={"price_per_qtl": 3105, "min_qty_qtl": 20}
                           ).json() == {"error": "BID_TOO_LOW", "min_next": 3110.0}
        second = client.post(url, headers=hdr(t2, "k3"), json={"price_per_qtl": 3110, "min_qty_qtl": 20})
        assert second.status_code == 201
        assert [b["status"] for b in client.get("/api/bids/mine", headers=hdr(t1)).json()["bids"]
                if b["cluster_id"] == cid] == ["OUTBID"]
        mine1 = client.get(f"/api/clusters/{cid}", headers=hdr(t1)).json()["best_bid"]
        mine2 = client.get(f"/api/clusters/{cid}", headers=hdr(t2)).json()["best_bid"]
        assert mine1 == {"price_per_qtl": 3110.0, "mine": False} and mine2["mine"] is True

        # --- round 1: nobody answers, deadline passes -> bid FAILED, cluster back to BIDDING (first failure) ---
        assert client.post(f"/api/admin/clusters/{cid}/close-auction", headers=hdr(t1)).status_code == 403
        assert client.post(f"/api/admin/clusters/{cid}/close-auction", headers=hdr(ta)).json() == {"status": "CONFIRMING"}
        prog = next(x for x in client.get("/api/bids/mine", headers=hdr(t2)).json()["bids"] if x["cluster_id"] == cid)
        assert prog["status"] == "CONFIRMING" and prog["progress"] == {"accepted_qtl": 0, "rejected_qtl": 0, "pending_qtl": 25}
        client.portal.call(db.pool.execute, "UPDATE bids SET confirm_deadline = now() - interval '1 second' "
                                            "WHERE cluster_id = $1::uuid AND status = 'CONFIRMING'", cid)
        client.portal.call(bidding.tick, db.pool)
        got = client.get(f"/api/clusters/{cid}", headers=hdr(t1)).json()
        assert got["status"] == "BIDDING" and got["best_bid"] is None
        assert next(x for x in client.get("/api/bids/mine", headers=hdr(t2)).json()["bids"]
                    if x["cluster_id"] == cid)["status"] == "FAILED"

        # --- round 2: buyer1 wins, 3 of 5 lots accept (15 q < min 20) -> fails again -> NO_BID ---
        client.post(url, headers=hdr(t1, "k4"), json={"price_per_qtl": 3100, "min_qty_qtl": 20})
        client.post(f"/api/admin/clusters/{cid}/close-auction", headers=hdr(ta))
        r = client.post(f"/api/admin/clusters/{cid}/simulate-farmers", headers=hdr(ta), json={"accepted_lots": 3})
        assert r.json()["outcome"] == "FAILED"
        assert client.get(f"/api/clusters/{cid}", headers=hdr(t1)).json()["status"] == "NO_BID"

        # --- round 3 on a fresh cluster is not possible for a NO_BID one; check the deal path on a new cluster ---
    asyncio.run(teardown5())
    farmers = asyncio.run(setup_farmers(5))
    with TestClient(app) as client:
        for i, (p, f) in enumerate(farmers):
            client.portal.call(clustering.commit_listing, db.pool, session(p, f, 5, 3000 + 10 * i))
        t1, b1 = login(client, "buyer1@demo.test")
        t2, _ = login(client, "buyer2@demo.test")
        ta, _ = login(client, "admin@demo.test")
        tag = client.post("/api/auth/agent/login", json={"phone": "+919800000099", "pin": "1234"}).json()["token"]
        cid = next(c["id"] for c in client.get("/api/clusters?status=READY", headers=hdr(t1)).json()["clusters"]
                   if c["collection_point"]["name"] == "D4 test yard")
        client.post(f"/api/agent/clusters/{cid}/verification", headers=hdr(tag), data=vform(), files=photo())
        base = client.portal.call(db.pool.fetchval, "SELECT COALESCE(MAX(seq),0) FROM events")
        with client.websocket_connect(f"/ws?token={t1}&since={base}") as w1, \
                client.websocket_connect(f"/ws?token={t2}&since={base}") as w2:
            client.post(f"/api/clusters/{cid}/bids", headers=hdr(t1, "d1"), json={"price_per_qtl": 3100, "min_qty_qtl": 20})
            m1 = [w1.receive_json() for _ in range(2)]
            m2 = [w2.receive_json() for _ in range(2)]
            assert [m["type"] for m in m1] == ["bid.placed", "cluster.updated"]
            assert m1[0]["payload"]["buyer_is_you"] is True and m2[0]["payload"]["buyer_is_you"] is False
            assert m1[1]["payload"]["best_bid"] == {"price_per_qtl": 3100.0, "mine": True}
            assert m2[1]["payload"]["best_bid"] == {"price_per_qtl": 3100.0, "mine": False}
            assert "buyer_id" not in str([m1, m2])
            client.post(f"/api/admin/clusters/{cid}/close-auction", headers=hdr(ta))
            assert client.post(f"/api/admin/clusters/{cid}/simulate-farmers", headers=hdr(ta), json={"accept": True}
                               ).json()["outcome"] == "DEAL"
            seen1 = [w1.receive_json()["type"] for _ in range(4)]
            assert seen1 == ["bid.confirming", "cluster.updated", "deal.created", "cluster.updated"]
            assert [w2.receive_json()["type"] for _ in range(2)] == ["cluster.updated", "cluster.updated"]  # no deal data

        deal = next(d for d in client.get("/api/deals/mine", headers=hdr(t1)).json()["deals"] if d["cluster_id"] == cid)
        assert deal["qty_qtl"] == 25 and deal["gross_value"] == 77500 and deal["platform_fee"] == 1162.5
        assert deal["status"] == "CONFIRMED" and deal["fpo"]["name"] == "Dev FPO"
        assert all(d["cluster_id"] != cid for d in client.get("/api/deals/mine", headers=hdr(t2)).json()["deals"])
        assert client.post(f"/api/deals/{deal['id']}/payment-reported", headers=hdr(t1), json={}).json()["error"] == "PAYMENT_REF_REQUIRED"
        assert client.post(f"/api/deals/{deal['id']}/payment-reported", headers=hdr(t2), json={"payment_ref": "X"}
                           ).status_code == 404                                   # someone else's deal
        assert client.post(f"/api/agent/deals/{deal['id']}/payment-confirmed", headers=hdr(tag)
                           ).json()["error"] == "PAYMENT_NOT_REPORTED"
        assert client.post(f"/api/deals/{deal['id']}/payment-reported", headers=hdr(t1), json={"payment_ref": "UTR123"}
                           ).json() == {"status": "PAYMENT_REPORTED"}
        assert client.post(f"/api/agent/deals/{deal['id']}/payment-confirmed", headers=hdr(tag)).json() == {"status": "PAID"}
        assert next(d for d in client.get("/api/deals/mine", headers=hdr(t1)).json()["deals"] if d["id"] == deal["id"])["status"] == "PAID"
        assert client.get(f"/api/clusters/{cid}", headers=hdr(t1)).json()["status"] == "DEAL"


async def test_many_simultaneous_bids_leave_exactly_one_leader(clean5):
    pool = await db.connect()
    await cache.connect()
    try:
        farmers = await setup_farmers(5)
        for i, (p, f) in enumerate(farmers):
            await clustering.commit_listing(pool, session(p, f, 5, 3000))
        cid = str(await pool.fetchval("SELECT id FROM clusters WHERE collection_point_id = $1::uuid", CP))
        await pool.execute("UPDATE clusters SET status = 'BIDDING' WHERE id = $1::uuid", cid)
        buyers = [str(r["id"]) for r in await pool.fetch("SELECT id FROM buyers WHERE email LIKE '%@demo.test' LIMIT 2")]

        async def go(i):
            try:
                return (await bidding.place_bid(pool, buyers[i % 2], cid, 3200, 10, f"c{i}"))[1]
            except ApiError as e:
                return e.body["error"]
        res = await asyncio.gather(*[go(i) for i in range(12)])
        assert res.count(True) == 1 and res.count("BID_TOO_LOW") == 11
        assert await pool.fetchval("SELECT count(*) FROM bids WHERE cluster_id = $1::uuid AND status = 'LEADING'", cid) == 1
        # the same key sent 8 times at once makes one bid
        same = await asyncio.gather(*[bidding.place_bid(pool, buyers[0], cid, 3300, 10, "dup") for _ in range(8)],
                                    return_exceptions=True)
        assert len({s[0]["id"] for s in same if not isinstance(s, Exception)}) == 1
        assert await pool.fetchval("SELECT count(*) FROM bids WHERE buyer_id=$1::uuid AND idempotency_key='dup'", buyers[0]) == 1
    finally:
        await pool.execute("UPDATE clusters SET best_bid_id = NULL WHERE collection_point_id = $1::uuid", CP)
        await cache.close()
        await db.close()
