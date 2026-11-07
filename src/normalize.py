"""Turn each manager's scraper output into one common table for the site.

Common columns:
    manager, name, rent_per_bed_min, rent_per_bed_max, beds_min, beds_max,
    available, url, scraped_on
"""

from __future__ import annotations

import pandas as pd

COLUMNS = [
    "manager", "name", "rent_per_bed_min", "rent_per_bed_max",
    "beds_min", "beds_max", "available", "url", "scraped_on",
]


def from_appfolio(df: pd.DataFrame) -> pd.DataFrame:
    """AppFolio rows are single units priced per unit: split rent evenly by bed.

    Studios (0 beds) count as 1 bed. Units with unknown beds get no per-bed price.
    """
    beds_for_split = df["beds"].clip(lower=1)
    per_bed = (df["rent"] / beds_for_split).round(0)
    out = pd.DataFrame({
        "manager": df["manager"],
        "name": df["address"].fillna(df["title"]),
        "rent_per_bed_min": per_bed,
        "rent_per_bed_max": per_bed,
        "beds_min": df["beds"],
        "beds_max": df["beds"],
        "available": df["available_raw"],
        "url": df["url"],
        "scraped_on": df["scraped_on"],
    })
    return out[COLUMNS]


def from_greenstreet(df: pd.DataFrame) -> pd.DataFrame:
    """Green Street rows are buildings that already list per-bed price ranges."""
    out = df.rename(columns={"available_raw": "available"})
    return out[COLUMNS]


def from_jsm(df: pd.DataFrame) -> pd.DataFrame:
    """JSM rows are unit types. Use JSM's per-person price when listed;
    otherwise split the unit price evenly by bed (studios count as 1 bed)."""
    beds_for_split = df["beds"].clip(lower=1)
    lo = df["rent_person_min"].fillna((df["rent_unit_min"] / beds_for_split).round(0))
    hi = df["rent_person_max"].fillna((df["rent_unit_max"] / beds_for_split).round(0))
    out = pd.DataFrame({
        "manager": df["manager"],
        "name": df["name"],
        "rent_per_bed_min": lo,
        "rent_per_bed_max": hi,
        "beds_min": df["beds"],
        "beds_max": df["beds"],
        "available": df["terms"],
        "url": df["url"],
        "scraped_on": df["scraped_on"],
    })
    return out[COLUMNS]


SOURCES = {
    "community-property-management": from_appfolio,
    "green-street-realty": from_greenstreet,
    "jsm-living": from_jsm,
}


def load_all(data_dir: str = "data") -> pd.DataFrame:
    """Newest CSV for each manager, converted to the common columns and stacked."""
    import glob

    frames = []
    for prefix, normalize in SOURCES.items():
        files = sorted(glob.glob(f"{data_dir}/{prefix}_*.csv"))
        if files:
            frames.append(normalize(pd.read_csv(files[-1])))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)