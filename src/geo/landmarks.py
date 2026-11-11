"""Campus places students measure distance to (the Quad, Grainger, the ARC, ...).

Usage (fills in any missing coordinates with the Census geocoder, then saves):
    python -m src.geo.landmarks

reference/landmarks.csv is committed with the code, so the site reads it directly.
Rows still missing coordinates are left out of the site until filled.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from src.geo.distance import haversine_mi

LANDMARKS_PATH = Path(__file__).resolve().parents[2] / "reference" / "landmarks.csv"
WALK_MPH = 3.0        # typical walking pace
BIKE_MPH = 10.0       # relaxed cycling pace
DETOUR = 1.3          # streets aren't straight lines: rough street-vs-straight-line factor


def load_landmarks(path: Path = LANDMARKS_PATH) -> pd.DataFrame:
    """Landmarks that have coordinates, in file order."""
    df = pd.read_csv(path)
    return df.dropna(subset=["lat", "lon"]).reset_index(drop=True)


def miles_to(df: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    """Straight-line miles from each row's lat/lon to one point (NaN if unknown)."""
    return pd.Series(
        [round(haversine_mi(a, b, lat, lon), 2) if pd.notna(a) and pd.notna(b) else float("nan")
         for a, b in zip(df["lat"], df["lon"])],
        index=df.index,
    )


def minutes(miles: pd.Series, mph: float) -> pd.Series:
    """Rough travel time: straight-line miles x DETOUR at a steady pace."""
    return (miles * DETOUR / mph * 60).round(0)


def main() -> None:
    from src.geo.geocode import census_lookup

    df = pd.read_csv(LANDMARKS_PATH)
    session = requests.Session()
    for i, row in df.iterrows():
        if pd.notna(row["lat"]) or pd.isna(row["address"]):
            continue
        hit = census_lookup(row["address"], session)
        if hit:
            df.loc[i, ["lat", "lon"]] = [round(hit[0], 6), round(hit[1], 6)]
            df.loc[i, "source"] = f"Census geocoder: {hit[2]}"
            print(f"found   {row['name']}: {hit[0]:.5f}, {hit[1]:.5f}  ({hit[2]})")
        else:
            print(f"MISSING {row['name']}: no match for {row['address']}")
    df.to_csv(LANDMARKS_PATH, index=False)


if __name__ == "__main__":
    main()
