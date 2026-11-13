"""Move the demo pickup point to where the demo really happens, so the 500 m check passes for the agent standing there. Owner: Darshan.

  python backend/scripts/set_venue.py --lat 12.9716 --lon 77.5946            # moves "Dev FPO yard"
  python backend/scripts/set_venue.py --lat 12.9716 --lon 77.5946 --name "Venue demo point"
  python backend/scripts/set_venue.py --list                                  # show every pickup point and its coordinates

Get the coordinates by right-clicking the spot in Google Maps (the first line of the menu is "lat, lon").
The check itself stays on: an agent more than 500 m away is still refused (TOO_FAR), which is part of the demo.
Run against the dev database. Clusters already waiting there are not touched.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402

from app.config import settings  # noqa: E402


async def main(lat, lon, name, list_only) -> int:
    c = await asyncpg.connect(settings.database_url)
    try:
        rows = await c.fetch("SELECT name, ST_Y(geog::geometry) AS lat, ST_X(geog::geometry) AS lon FROM collection_points ORDER BY name")
        if list_only:
            for r in rows:
                print(f"  {r['name']:<22} {r['lat']:.5f}, {r['lon']:.5f}")
            return 0
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            print("Give valid --lat and --lon (for example 12.9716 and 77.5946).")
            return 1
        old = next((r for r in rows if r["name"] == name), None)
        if not old:
            print(f"No pickup point named '{name}'. Existing: {', '.join(r['name'] for r in rows)}")
            return 1
        await c.execute("UPDATE collection_points SET geog = ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography WHERE name = $3", lat, lon, name)
        print(f"'{name}' moved from {old['lat']:.5f}, {old['lon']:.5f} to {lat:.5f}, {lon:.5f}. "
              f"An agent within {settings.verify_radius_m} m of the new point can now verify.")
        return 0
    finally:
        await c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--name", default="Dev FPO yard")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.lat, a.lon, a.name, a.list)))
