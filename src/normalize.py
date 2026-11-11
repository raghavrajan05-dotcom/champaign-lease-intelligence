"""Turn each manager's scraper output into one common table for the site.

Common columns:
    manager, name, rent_per_bed_min, rent_per_bed_max, beds_min, beds_max,
    available, url, scraped_on
"""

from __future__ import annotations

from pathlib import Path

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
    "jsm-living": from_jsm,
}

# Buildings shown WITHOUT prices: their manager declined to let us use price data,
# so only the building's address and a link to the manager's site are listed.
# A fixed list (not scraped daily). Columns: manager, name, url, listed_as_of.
UNPRICED_PATH = Path(__file__).resolve().parents[1] / "reference" / "unpriced_buildings.csv"


def load_unpriced_buildings(path: Path = UNPRICED_PATH) -> pd.DataFrame:
    """Price-free building list in the common columns (prices and beds left empty)."""
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    out = pd.DataFrame({
        "manager": df["manager"],
        "name": df["name"],
        "rent_per_bed_min": float("nan"),
        "rent_per_bed_max": float("nan"),
        "beds_min": float("nan"),
        "beds_max": float("nan"),
        "available": "See manager's site",
        "url": df["url"],
        "scraped_on": df["listed_as_of"],
    })
    return out[COLUMNS]


# Public copy of the daily data: the workflow writes the newest file per manager
# to latest/<manager>.csv on the repo's "data" branch.
REMOTE_BASE = ("https://raw.githubusercontent.com/"
               "raghavrajan05-dotcom/champaign-lease-intelligence/data")


def load_latest_remote(base: str = REMOTE_BASE) -> pd.DataFrame:
    """Newest listings per manager, read over the internet (used by the hosted site)."""
    frames = []
    for prefix, normalize in SOURCES.items():
        try:
            frames.append(normalize(pd.read_csv(f"{base}/latest/{prefix}.csv")))
        except OSError:  # 404 / network error: that manager has no public file yet
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def load_all(data_dir: str = "data") -> pd.DataFrame:
    """Newest CSV for each manager, converted to the common columns and stacked."""
    import glob

    frames = []
    for prefix, normalize in SOURCES.items():
        files = sorted(glob.glob(f"{data_dir}/{prefix}_*.csv"))
        if files:
            frames.append(normalize(pd.read_csv(files[-1])))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
