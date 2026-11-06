"""Turn listing addresses into map coordinates with the free US Census geocoder.

Usage:
    python -m src.geo.geocode

Looks up every address in the latest scrapes that isn't already in
reference/geocodes.csv, then saves the results there. That file is committed,
so each address is only looked up once.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import requests

from src.geo.distance import dist_to_quad_mi

API_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CACHE_PATH = Path("reference/geocodes.csv")
CACHE_COLUMNS = ["name", "lat", "lon", "matched_address"]
MAX_MILES_FROM_QUAD = 5  # a "match" farther than this is almost surely the wrong place
CITY_RE = re.compile(r",\s*(Champaign|Urbana|Savoy)\b", re.I)


def clean_address(name: str) -> str:
    """'306-410 E. Michigan' -> '306 E Michigan'"""
    s = name.replace(".", "")
    s = re.sub(r"^(\d+)\s*-\s*\d+", r"\1", s.strip())  # building ranges: keep first number
    return re.sub(r"\s+", " ", s)


def candidates(name: str) -> list[str]:
    """Addresses to try, in order. Names without a city try Champaign, then Urbana."""
    s = clean_address(name)
    if CITY_RE.search(s):
        return [s]
    return [f"{s}, Champaign, IL", f"{s}, Urbana, IL"]


def census_lookup(address: str, session: requests.Session) -> tuple[float, float, str] | None:
    params = {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    resp = session.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    matches = resp.json()["result"]["addressMatches"]
    if not matches:
        return None
    top = matches[0]
    return top["coordinates"]["y"], top["coordinates"]["x"], top["matchedAddress"]


def geocode(name: str, session: requests.Session) -> dict:
    for address in candidates(name):
        hit = census_lookup(address, session)
        if hit:
            lat, lon, matched = hit
            if dist_to_quad_mi(lat, lon) <= MAX_MILES_FROM_QUAD:
                return {"name": name, "lat": lat, "lon": lon, "matched_address": matched}
    return {"name": name, "lat": None, "lon": None, "matched_address": None}


def load_cache(path: Path = CACHE_PATH) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=CACHE_COLUMNS)


def attach_distance(listings: pd.DataFrame, cache: pd.DataFrame) -> pd.DataFrame:
    """Add lat, lon and miles_to_quad columns by matching on the listing name."""
    out = listings.merge(cache[["name", "lat", "lon"]], on="name", how="left")
    out["miles_to_quad"] = [
        dist_to_quad_mi(lat, lon) if pd.notna(lat) else None
        for lat, lon in zip(out["lat"], out["lon"])
    ]
    return out


def main() -> None:
    from src.normalize import load_all

    names = load_all()["name"].dropna().unique()
    cache = load_cache()
    todo = [n for n in names if n not in set(cache["name"])]
    print(f"{len(names)} addresses, {len(todo)} not looked up yet")

    session = requests.Session()
    new_rows = []
    for i, name in enumerate(todo, 1):
        new_rows.append(geocode(name, session))
        time.sleep(0.3)  # be polite to the free API
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}")

    if new_rows:
        cache = pd.concat([cache, pd.DataFrame(new_rows)], ignore_index=True)
        CACHE_PATH.parent.mkdir(exist_ok=True)
        cache.to_csv(CACHE_PATH, index=False)

    missed = [r["name"] for r in new_rows if r["lat"] is None]
    print(f"matched {len(new_rows) - len(missed)}, unmatched {len(missed)}")
    for name in missed[:20]:
        print("  no match:", name)


if __name__ == "__main__":
    main()