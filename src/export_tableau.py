"""Export one clean, combined table for Tableau.

Usage:
    python -m src.export_tableau

Writes exports/listings_for_tableau.csv: the newest listings from every
manager, in the site's common columns, plus coordinates, distance to the Quad,
a distance band and a single "typical" rent per bed for charting.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.geo.geocode import attach_distance, load_cache
from src.normalize import load_all

OUT_PATH = Path("exports/listings_for_tableau.csv")
BANDS = [(0.5, "Under 0.5 mi"), (1.0, "0.5-1 mi"), (2.0, "1-2 mi"), (float("inf"), "2+ mi")]
LISTING_TYPE = {
    "Green Street Realty": "Building (price range)",
    "JSM Living": "Unit type",
    "Community Property Management": "Single unit",
}


def distance_band(miles: float | None) -> str:
    if miles is None or pd.isna(miles):
        return "Unknown"
    for limit, label in BANDS:
        if miles < limit:
            return label
    return "Unknown"


def build() -> pd.DataFrame:
    df = attach_distance(load_all(), load_cache())
    df["rent_per_bed_mid"] = (df["rent_per_bed_min"] + df["rent_per_bed_max"]) / 2
    df["distance_band"] = df["miles_to_quad"].map(distance_band)
    df["listing_type"] = df["manager"].map(LISTING_TYPE).fillna("Other")
    df = df.rename(columns={"lat": "Latitude", "lon": "Longitude", "beds_min": "beds"})
    cols = ["manager", "listing_type", "name", "beds", "rent_per_bed_min", "rent_per_bed_max",
            "rent_per_bed_mid", "miles_to_quad", "distance_band", "Latitude", "Longitude",
            "available", "scraped_on", "url"]
    return df[cols]


def main() -> None:
    df = build()
    OUT_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"{len(df)} rows -> {OUT_PATH}")
    print(df.groupby("manager").agg(rows=("name", "size"),
                                    median_rent_per_bed=("rent_per_bed_mid", "median"),
                                    located=("Latitude", "count")).to_string())


if __name__ == "__main__":
    main()
