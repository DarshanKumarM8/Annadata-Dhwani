"""Exotel setup checker for the live spike (D7). Owner: Darshan.

  python backend/scripts/exotel_check.py          # which settings are missing + the URLs to paste into Exotel
  python backend/scripts/exotel_check.py --ping   # also check that PUBLIC_BASE_URL reaches this server (GET /health only)

It never places a call and never sends a missed-call webhook (that would ring a real phone). The URLs contain
WEBHOOK_SECRET: use them in the Exotel dashboard only, do not paste them in the group chat or screenshots.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.config import settings as s  # noqa: E402

WANT = {"EXOTEL_SID": s.exotel_sid, "EXOTEL_API_KEY": s.exotel_api_key, "EXOTEL_API_TOKEN": s.exotel_api_token,
        "EXOPHONE": s.exophone, "EXOTEL_APP_ID": s.exotel_app_id, "WEBHOOK_SECRET": s.webhook_secret}


def main(ping: bool) -> int:
    bad = 0
    print("Settings")
    for k, v in WANT.items():
        ok = bool(v)
        bad += not ok
        print(f"  {'ok     ' if ok else 'MISSING'} {k}")
    if len(s.webhook_secret) < 24:
        print("  WARN    WEBHOOK_SECRET is short; use 32+ random characters (the secret is the only protection)")
        bad += 1
    pub = s.public_base_url.rstrip("/")
    local = "localhost" in pub or "127.0.0.1" in pub
    print(f"\nPUBLIC_BASE_URL = {pub}")
    if local or not pub.startswith("https://"):
        print("  MISSING an https public URL (ngrok). Exotel and phones cannot reach localhost.")
        bad += 1
    if s.provider != "exotel":
        print(f"  NOTE    TELEPHONY_PROVIDER={s.provider}: real numbers are not called until it is 'exotel'.")
    root = f"{pub}/tel/exotel/{s.webhook_secret}"
    print("\nPaste into the Exotel dashboard")
    print(f"  ExoPhone missed-call webhook (POST) : {root}/missed")
    print(f"  Gather applet 1..12 (dynamic URL)    : {root}/gather?step=<k>")
    print(f"  Passthru applet 1..12 (URL)          : {root}/digits?step=<k>")
    print("  (each Passthru's failure branch -> Hangup; save the flow as `annadata-ivr`, copy its App ID to EXOTEL_APP_ID)")
    print(f"  StatusCallback (set by us per call)  : {root}/status")
    if ping:
        try:
            r = httpx.get(f"{pub}/health", timeout=8)
            print(f"\nPing {pub}/health -> HTTP {r.status_code} {r.text[:80]}")
            bad += r.status_code != 200
        except Exception as e:
            print(f"\nPing failed: {type(e).__name__}: {e}")
            bad += 1
    print("\nREADY for the live spike" if not bad else f"\n{bad} thing(s) to fix before the live spike")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ping", action="store_true")
    sys.exit(main(ap.parse_args().ping))
