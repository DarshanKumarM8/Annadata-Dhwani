#!/usr/bin/env python3
"""Ingest mandi prices from data.gov.in and compute AFPP price floors.

Usage
-----
Live API::

    DATA_GOV_KEY=<key> DATABASE_URL=postgresql://… REDIS_URL=redis://…  \
        python backend/scripts/ingest_prices.py

From fixture files (no network)::

    python backend/scripts/ingest_prices.py --from-fixtures contracts/fixtures
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import asyncpg
import httpx
import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Allow ``from pricing import …`` without __init__.py files.
# ---------------------------------------------------------------------------
_services = str(Path(__file__).resolve().parent.parent / "app" / "services")
if _services not in sys.path:
    sys.path.insert(0, _services)

from pricing import (  # noqa: E402
    IST,
    compute_afpp,
    filter_outliers,
    safe_median,
    today_ist,
)

logger = logging.getLogger(__name__)

API_URL = (
    "https://api.data.gov.in/resource/"
    "9ef84268-d588-465a-a308-a864a43d0070"
)


# ---- helpers ---------------------------------------------------------------


def _file_token(value: str) -> str:
    """Lower-case, alphanumeric-only token for fixture filenames."""
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _parse_date(s: str) -> date:
    """Parse ``DD/MM/YYYY`` or ``YYYY-MM-DD`` → :class:`datetime.date`."""
    s = s.strip()
    if "/" in s:
        return datetime.strptime(s, "%d/%m/%Y").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _safe_float(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---- data sources ----------------------------------------------------------


def _load_fixture(
    fixtures_dir: str,
    district_name: str,
    agmark_name: str,
    crop_code: str = "",
) -> list[dict]:
    """Read ``agmark_<district>_<crop>.json`` from *fixtures_dir*."""
    d_dir = Path(fixtures_dir)
    tokens_district = {_file_token(district_name)}
    tokens_crop = {_file_token(agmark_name)}
    if crop_code:
        tokens_crop.add(_file_token(crop_code))

    candidates: list[Path] = []
    for td in tokens_district:
        for tc in tokens_crop:
            candidates.append(d_dir / f"agmark_{td}_{tc}.json")
            candidates.append(d_dir / f"agmark_{td}_{tc}_fallback.json")

    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                recs = data.get("records", [])
                if isinstance(recs, list) and recs:
                    for r in recs:
                        if not r.get("district"):
                            r["district"] = district_name
                    return recs
            except Exception:
                pass

    if d_dir.exists():
        for path in d_dir.glob("agmark_*.json"):
            stem = path.stem.lower()
            if any(td in stem for td in tokens_district) and any(
                tc in stem for tc in tokens_crop
            ):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    recs = data.get("records", [])
                    if isinstance(recs, list) and recs:
                        for r in recs:
                            if not r.get("district"):
                                r["district"] = district_name
                        return recs
                except Exception:
                    pass

    return []


async def _fetch_api(
    client: httpx.AsyncClient,
    api_key: str,
    agmark_state: str,
    agmark_name: str,
) -> list[dict]:
    """Fetch with 3 retries, 10 s timeout, backoff 1 / 2 / 4 s."""
    params: dict[str, str | int] = {
        "api-key": api_key,
        "format": "json",
        "limit": 1000,
        "filters[state.keyword]": agmark_state,
        "filters[commodity]": agmark_name,
    }
    backoffs = (1, 2, 4)
    for attempt in range(3):
        try:
            resp = await client.get(API_URL, params=params, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            recs = data.get("records", [])
            return recs if isinstance(recs, list) else []
        except Exception as exc:
            logger.warning(
                "Attempt %d for %s / %s: %s",
                attempt + 1,
                agmark_state,
                agmark_name,
                exc,
            )
            if attempt < 2:
                await asyncio.sleep(backoffs[attempt])
    logger.error("All retries exhausted for %s / %s", agmark_state, agmark_name)
    return []


# ---- Core Reusable Ingestion Logic ----------------------------------------


async def ingest_prices(
    pool: asyncpg.Pool,
    rds: aioredis.Redis | None = None,
    api_key: str = "",
    fixtures_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Ingest mandi prices, persist to DB, compute AFPP and cache in Redis."""
    # 1. Load reference data
    async with pool.acquire() as conn:
        districts = await conn.fetch(
            "SELECT code, name, agmark_state, agmark_district FROM districts"
        )
        crops = await conn.fetch("SELECT code, agmark_name FROM crops")
        deductions = {
            r["district_code"]: r
            for r in await conn.fetch(
                "SELECT district_code, transport_per_qtl, handling_per_qtl, "
                "pct_deduction FROM deduction_rules"
            )
        }

    today = today_ist()
    now_utc = datetime.now(timezone.utc)

    # 2. Fetch raw data per (state, commodity)
    call_cache: dict[tuple[str, str], list[dict]] = {}

    async with httpx.AsyncClient() as client:
        for crop in crops:
            for d in districts:
                key = (d["agmark_state"], crop["agmark_name"])
                if key in call_cache:
                    continue

                if fixtures_dir:
                    combined: list[dict] = []
                    for dd in districts:
                        if dd["agmark_state"] == d["agmark_state"]:
                            combined.extend(
                                _load_fixture(
                                    fixtures_dir,
                                    dd["name"],
                                    crop["agmark_name"],
                                    crop["code"],
                                )
                            )
                    call_cache[key] = combined
                else:
                    if not api_key:
                        logger.warning(
                            "DATA_GOV_KEY not set and no fixtures_dir provided."
                        )
                        call_cache[key] = []
                    else:
                        call_cache[key] = await _fetch_api(
                            client,
                            api_key,
                            d["agmark_state"],
                            crop["agmark_name"],
                        )

    # 3. Process per district × crop
    results: list[dict[str, Any]] = []

    for district in districts:
        for crop in crops:
            dc = district["code"]
            cc = crop["code"]
            agmark_dist = district["agmark_district"]
            dist_name = district["name"]
            key = (district["agmark_state"], crop["agmark_name"])
            all_records = call_cache.get(key, [])

            match_names = {agmark_dist.lower(), dist_name.lower()}
            district_recs = [
                r
                for r in all_records
                if str(r.get("district", "")).strip().lower() in match_names
            ]

            parsed: list[dict] = []
            for r in district_recs:
                modal = _safe_float(r.get("modal_price"))
                if modal is None:
                    continue
                try:
                    pd = _parse_date(str(r["arrival_date"]))
                except (KeyError, ValueError):
                    continue
                parsed.append(
                    {
                        "market": str(r.get("market", "")),
                        "price_date": pd,
                        "min_price": _safe_float(r.get("min_price")),
                        "max_price": _safe_float(r.get("max_price")),
                        "modal_price": modal,
                    }
                )

            state_modals: list[float] = [
                m
                for r in all_records
                if (m := _safe_float(r.get("modal_price"))) is not None
            ]

            # Upsert into mandi_prices
            async with pool.acquire() as conn:
                for rec in parsed:
                    await conn.execute(
                        """
                        INSERT INTO mandi_prices (
                            district_code, crop_code, market, price_date,
                            min_price, max_price, modal_price, source, fetched_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (district_code, crop_code, market, price_date)
                        DO UPDATE SET
                            min_price = EXCLUDED.min_price,
                            max_price = EXCLUDED.max_price,
                            modal_price = EXCLUDED.modal_price,
                            source = EXCLUDED.source,
                            fetched_at = EXCLUDED.fetched_at
                        """,
                        dc,
                        cc,
                        rec["market"],
                        rec["price_date"],
                        rec["min_price"],
                        rec["max_price"],
                        rec["modal_price"],
                        "data.gov.in" if not fixtures_dir else "fixture",
                        now_utc,
                    )

                stored_rows = await conn.fetch(
                    """
                    SELECT modal_price, price_date FROM mandi_prices
                    WHERE district_code = $1 AND crop_code = $2
                      AND price_date >= $3
                    ORDER BY price_date DESC
                    """,
                    dc,
                    cc,
                    today - timedelta(days=7),
                )

            stored_modals = [float(r["modal_price"]) for r in stored_rows]
            filtered = filter_outliers(stored_modals)

            if stored_modals:
                med = median(stored_modals)
                filtered_rows = [
                    r
                    for r in stored_rows
                    if med <= 0
                    or abs(float(r["modal_price"]) - med) / med <= 0.4
                ]
            else:
                filtered_rows = []

            newest_date: date | None = (
                filtered_rows[0]["price_date"] if filtered_rows else None
            )

            basis: str | None = None
            floor_modal: float | None = None
            price_date_used: date | None = None

            # 1. DISTRICT_FRESH (within 2 days)
            if newest_date and 0 <= (today - newest_date).days <= 2:
                fresh = [
                    float(r["modal_price"])
                    for r in filtered_rows
                    if r["price_date"] == newest_date
                ]
                if fresh:
                    floor_modal = median(fresh)
                    basis = "DISTRICT_FRESH"
                    price_date_used = newest_date

            # 2. DISTRICT_7D
            if basis is None and filtered:
                floor_modal = median(filtered)
                basis = "DISTRICT_7D"
                price_date_used = newest_date or today

            # 3. STATE_7D
            if basis is None and state_modals:
                floor_modal = median(state_modals)
                basis = "STATE_7D"
                state_dates: list[date] = []
                for r in all_records:
                    try:
                        state_dates.append(_parse_date(str(r["arrival_date"])))
                    except (KeyError, ValueError):
                        pass
                price_date_used = max(state_dates) if state_dates else today

            if basis is None or floor_modal is None or price_date_used is None:
                logger.info("No floor data for %s / %s", dc, cc)
                results.append(
                    {
                        "district_code": dc,
                        "crop_code": cc,
                        "modal_price": None,
                        "afpp": None,
                        "basis": "NO_DATA",
                        "price_date": None,
                    }
                )
                continue

            ded = deductions.get(dc)
            if ded:
                afpp = compute_afpp(
                    floor_modal,
                    float(ded["pct_deduction"]),
                    float(ded["transport_per_qtl"]),
                    float(ded["handling_per_qtl"]),
                )
            else:
                afpp = compute_afpp(floor_modal, 0, 0, 0)

            # Upsert into price_floors
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO price_floors (
                        district_code, crop_code, as_of, price_date,
                        modal_price, afpp, basis
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (district_code, crop_code, as_of)
                    DO UPDATE SET
                        price_date = EXCLUDED.price_date,
                        modal_price = EXCLUDED.modal_price,
                        afpp = EXCLUDED.afpp,
                        basis = EXCLUDED.basis
                    """,
                    dc,
                    cc,
                    today,
                    price_date_used,
                    floor_modal,
                    afpp,
                    basis,
                )

            # Cache in Redis
            cache_obj = {
                "modal_price": floor_modal,
                "afpp": afpp,
                "basis": basis,
                "price_date": price_date_used.isoformat(),
            }
            if rds is not None:
                try:
                    await rds.set(
                        f"floor:{dc}:{cc}", json.dumps(cache_obj), ex=93600
                    )
                except Exception as exc:
                    logger.warning("Redis cache failed for floor:%s:%s: %s", dc, cc, exc)

            results.append(
                {
                    "district_code": dc,
                    "crop_code": cc,
                    "modal_price": floor_modal,
                    "afpp": afpp,
                    "basis": basis,
                    "price_date": price_date_used.isoformat(),
                }
            )

    return results


# ---- CLI main --------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest mandi prices & compute AFPP floors"
    )
    parser.add_argument(
        "--from-fixtures",
        metavar="DIR",
        help="Read fixture JSON files from DIR instead of calling the live API",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/annadata")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    api_key = os.environ.get("DATA_GOV_KEY", "")

    pool = await asyncpg.create_pool(db_url)
    rds = aioredis.from_url(redis_url)

    try:
        results = await ingest_prices(
            pool=pool,
            rds=rds,
            api_key=api_key,
            fixtures_dir=args.from_fixtures,
        )

        hdr = (
            f"{'District':<12} {'Crop':<15} "
            f"{'Modal':>8} {'AFPP':>8} "
            f"{'Basis':<16} {'Price Date'}"
        )
        print(f"\n{hdr}")
        print("-" * len(hdr))
        for r in results:
            modal_str = f"{r['modal_price']:.0f}" if r["modal_price"] is not None else "-"
            afpp_str = str(r["afpp"]) if r["afpp"] is not None else "-"
            print(
                f"{r['district_code']:<12} {r['crop_code']:<15} "
                f"{modal_str:>8} {afpp_str:>8} "
                f"{r['basis']:<16} {r['price_date'] or '-'}"
            )
        print()
    finally:
        await pool.close()
        await rds.aclose()


if __name__ == "__main__":
    asyncio.run(main())
