"""Turn each manager's scraper output into one common table for the site.

Common columns:
    manager, listing_id, name, rent_per_bed_min, rent_per_bed_max, beds_min, beds_max,
    available, url, scraped_on, status

status: Available, Last unit, Leased, Sold out or Unavailable (as the manager shows it).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

COLUMNS = [
    "manager", "listing_id", "name", "rent_per_bed_min", "rent_per_bed_max",
    "beds_min", "beds_max", "available", "url", "scraped_on", "status",
]
OPEN_STATUSES = ("Available", "Last unit")  # anything else is leased / sold out / unavailable


def _ids(df: pd.DataFrame, fallback: str) -> pd.Series:
    """The manager's own listing ID (stable day to day); fallback column if a file lacks it."""
    col = "external_id" if "external_id" in df else fallback
    return df[col].astype(str)


# Listings whose text says the price is for one bedroom, not the whole unit.
PER_PERSON_RE = (r"individual|per[ -]person|per[ -]bed\b|by[ -]the[ -]bed|roommate matching"
                 r"|bedrooms? available|furnished bedrooms")
MIN_PLAUSIBLE_PER_BED = 200  # a whole-unit rent split below this is almost surely per person


def per_person_mask(text: pd.Series, rent: pd.Series, beds: pd.Series) -> pd.Series:
    """True where `rent` is already a per-bed price: the listing says so, or splitting it
    across the bedrooms would give an implausibly low price."""
    says_so = text.fillna("").str.contains(PER_PERSON_RE, case=False, regex=True)
    too_low = (rent / beds.clip(lower=1)) < MIN_PLAUSIBLE_PER_BED
    return says_so | too_low.fillna(False)


def from_appfolio(df: pd.DataFrame) -> pd.DataFrame:
    """AppFolio rows are single units, usually priced per unit: split rent evenly by bed.

    Studios (0 beds) count as 1 bed. Units with unknown beds get no per-bed price.
    Rooms advertised individually ("individual leases", "per person") keep their price.
    """
    beds_for_split = df["beds"].clip(lower=1)
    text = df["title"] if "title" in df else pd.Series("", index=df.index)
    per_person = per_person_mask(text, df["rent"], df["beds"])
    per_bed = (df["rent"] / beds_for_split).round(0).where(~per_person, df["rent"])
    out = pd.DataFrame({
        "manager": df["manager"],
        "listing_id": _ids(df, "address"),
        "name": df["address"].fillna(df["title"]),
        "rent_per_bed_min": per_bed,
        "rent_per_bed_max": per_bed,
        "beds_min": df["beds"],
        "beds_max": df["beds"],
        "available": df["available_raw"],
        "url": df["url"],
        "scraped_on": df["scraped_on"],
        "status": "Available",  # AppFolio only lists units that are for rent
    })
    return out[COLUMNS]


def from_greenstreet(df: pd.DataFrame) -> pd.DataFrame:
    """Green Street rows are buildings that already list per-bed price ranges."""
    out = df.rename(columns={"available_raw": "available"})
    out["listing_id"] = _ids(out, "name")
    out["status"] = "Available"
    return out[COLUMNS]


def from_jsm(df: pd.DataFrame) -> pd.DataFrame:
    """JSM rows are unit types. Use JSM's per-person price when listed;
    otherwise split the unit price evenly by bed (studios count as 1 bed)."""
    beds_for_split = df["beds"].clip(lower=1)
    lo = df["rent_person_min"].fillna((df["rent_unit_min"] / beds_for_split).round(0))
    hi = df["rent_person_max"].fillna((df["rent_unit_max"] / beds_for_split).round(0))
    out = pd.DataFrame({
        "manager": df["manager"],
        "listing_id": _ids(df, "name"),
        "name": df["name"],
        "rent_per_bed_min": lo,
        "rent_per_bed_max": hi,
        "beds_min": df["beds"],
        "beds_max": df["beds"],
        "available": df["terms"],
        "url": df["url"],
        "scraped_on": df["scraped_on"],
        "status": "Available",
    })
    return out[COLUMNS]


def from_standard(df: pd.DataFrame) -> pd.DataFrame:
    """Scrapers built on src/scrapers/common.py already write per-bed prices and a status."""
    out = pd.DataFrame({
        "manager": df["manager"],
        "listing_id": _ids(df, "name"),
        "name": df["name"],
        "rent_per_bed_min": df["rent_per_bed_min"],
        "rent_per_bed_max": df["rent_per_bed_max"],
        "beds_min": df["beds"],
        "beds_max": df["beds"],
        "available": df["available"],
        "url": df["url"],
        "scraped_on": df["scraped_on"],
        "status": df["status"].fillna("Available"),
    })
    return out[COLUMNS]


SOURCES = {
    "community-property-management": from_appfolio,
    "green-street-realty": from_greenstreet,
    "jsm-living": from_jsm,
    # More managers on AppFolio: same scraper, same columns (see the workflow).
    "ramshaw-real-estate": from_appfolio,
    "weiner-companies": from_appfolio,
    # Scrapers that write the standard layout (src/scrapers/common.py).
    "roland-realty": from_standard,
    "mhm-properties": from_standard,
    "smile-student-living": from_standard,
    "octave": from_standard,
    "seven07": from_standard,
    "the-rive": from_standard,
}

# Buildings shown WITHOUT prices, e.g. when a manager doesn't allow price data:
# only the building's address and a link to the manager's site are listed.
# A fixed list (not scraped daily). Columns: manager, name, url, listed_as_of.
UNPRICED_PATH = Path(__file__).resolve().parents[1] / "reference" / "unpriced_buildings.csv"


def load_unpriced_buildings(path: Path = UNPRICED_PATH) -> pd.DataFrame:
    """Price-free building list in the common columns (prices and beds left empty)."""
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    out = pd.DataFrame({
        "manager": df["manager"],
        "listing_id": df["name"],
        "name": df["name"],
        "rent_per_bed_min": float("nan"),
        "rent_per_bed_max": float("nan"),
        "beds_min": float("nan"),
        "beds_max": float("nan"),
        "available": "See manager's site",
        "url": df["url"],
        "scraped_on": df["listed_as_of"],
        "status": "Available",
    })
    return out[COLUMNS]


# Public copy of the daily data: the workflow writes the newest file per manager
# to latest/<manager>.csv on the repo's "data" branch.
REPO = "raghavrajan05-dotcom/champaign-lease-intelligence"
REMOTE_BASE = f"https://raw.githubusercontent.com/{REPO}/data"
HISTORY_DAYS = 30  # how far back the site's trend charts look


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


def _stack(files_by_prefix: dict[str, list[str]], read) -> pd.DataFrame:
    frames = []
    for prefix, files in files_by_prefix.items():
        normalize = SOURCES[prefix]
        for f in sorted(files)[-HISTORY_DAYS:]:
            try:
                frames.append(normalize(read(f)))
            except (OSError, KeyError):  # missing file or an old column layout
                continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def load_history(data_dir: str = "data") -> pd.DataFrame:
    """Every daily scrape (last HISTORY_DAYS per manager), stacked: one row per listing per day."""
    import glob

    files = {p: glob.glob(f"{data_dir}/{p}_*.csv") for p in SOURCES}
    return _stack(files, pd.read_csv)


def load_history_remote(repo: str = REPO, base: str = REMOTE_BASE) -> pd.DataFrame:
    """Same as load_history, read from the public data branch (used by the hosted site).

    One GitHub API call lists the files; the CSVs themselves come from raw.githubusercontent.com.
    """
    import requests

    try:
        resp = requests.get(f"https://api.github.com/repos/{repo}/git/trees/data",
                            params={"recursive": "1"}, timeout=20)
        resp.raise_for_status()
        paths = [t["path"] for t in resp.json().get("tree", [])]
    except (requests.RequestException, ValueError):
        return pd.DataFrame(columns=COLUMNS)
    files = {p: [x for x in paths if x.startswith(f"data/{p}_") and x.endswith(".csv")]
             for p in SOURCES}
    return _stack(files, lambda path: pd.read_csv(f"{base}/{path}"))
