"""Fetch real Agmarknet mandi price samples for Mandya and Mysuru.

Set DATA_GOV_IN_API_KEY in the environment before running this script.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx


API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
API_KEY = "579b464db66ec23bdd00000167f01a8cbbfd4b815b8247cdd8fe0063"
STATE = "Karnataka"
DISTRICTS = ("Mandya", "Mysuru")
COMMODITIES = ("Ragi (Finger Millet)", "Paddy(Dhan)(Common)", "Maize")
OUTPUT_DIR = Path(__file__).resolve().parent / "contracts" / "fixtures"


def file_token(value: str) -> str:
    """Make a readable, stable filename token without changing query values."""
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def records_from(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records", [])
    return records if isinstance(records, list) else []


def save_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fetch_json(
    client: httpx.Client,
    api_key: str,
    district: str,
    commodity: str | None = None,
) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "api-key": api_key,
        "format": "json",
        "limit": 100,
        "filters[state.keyword]": STATE,
        "filters[district]": district,
    }
    if commodity is not None:
        params["filters[commodity]"] = commodity

    response = client.get(API_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected JSON response for {district}: expected an object")
    return payload


def main() -> int:
    api_key = os.environ.get("DATA_GOV_IN_API_KEY", API_KEY).strip()
    if not api_key:
        print(
            "Set DATA_GOV_IN_API_KEY to your data.gov.in key, then run this script again.",
            file=sys.stderr,
        )
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=90.0) as client:
            for district in DISTRICTS:
                for commodity in COMMODITIES:
                    payload = fetch_json(client, api_key, district, commodity)
                    records = records_from(payload)
                    stem = f"agmark_{file_token(district)}_{file_token(commodity)}"
                    save_payload(OUTPUT_DIR / f"{stem}.json", payload)
                    returned_names = sorted(
                        {
                            str(record["commodity"])
                            for record in records
                            if record.get("commodity") is not None
                        }
                    )
                    print(
                        f"{district} | requested {commodity!r} | "
                        f"{len(records)} rows | returned commodity strings: "
                        f"{[repr(name) for name in returned_names]}"
                    )

                    if not records:
                        fallback = fetch_json(client, api_key, district)
                        fallback_records = records_from(fallback)
                        save_payload(
                            OUTPUT_DIR / f"{stem}_fallback.json", fallback
                        )
                        distinct_names = sorted(
                            {
                                str(record["commodity"])
                                for record in fallback_records
                                if record.get("commodity") is not None
                            }
                        )
                        print(
                            f"{district} | district-only retry | "
                            f"{len(fallback_records)} rows | distinct exact commodity "
                            f"strings: {[repr(name) for name in distinct_names]}"
                        )
    except httpx.HTTPStatusError as exc:
        print(
            f"Fetch failed: HTTP {exc.response.status_code} "
            f"{exc.response.reason_phrase}",
            file=sys.stderr,
        )
        return 1
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        # Exception messages may contain the full request URL, including the key.
        print(f"Fetch failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(f"Raw JSON fixtures saved under: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
