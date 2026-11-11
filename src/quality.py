"""Daily data-quality checks on the newest scrape for each manager.

Usage:
    python -m src.quality

Prints a report (and writes it to the GitHub Actions run summary when running
there). Exits with code 1 if any check FAILS, so a bad day is flagged instead
of silently flowing into the site.
"""

from __future__ import annotations

import glob
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from src.normalize import COLUMNS, SOURCES

MAX_COUNT_DROP = 0.5        # fail if listings fall by more than 50% vs the previous scrape
MAX_MISSING_PRICE = 0.25    # fail if more than 25% of rows have no per-bed price
RENT_PER_BED_RANGE = (200, 3000)  # $/bed/month outside this is almost surely a parsing error
MAX_AGE_DAYS = 3            # fail if a manager's newest scrape is older than this (e.g. the laptop job stopped)

# Sources deliberately not scraped right now, with the reason. They are reported
# as SKIP instead of failing every run (an alert that always fires gets ignored).
PAUSED: dict[str, str] = {}  # e.g. {"jsm-living": "paused: site down for maintenance"}


@dataclass
class Check:
    manager: str
    name: str
    passed: bool
    detail: str
    skipped: bool = False

    def __post_init__(self):
        self.passed = bool(self.passed)  # pandas comparisons return numpy bools


def latest_two(prefix: str, data_dir: str = "data") -> tuple[str | None, str | None]:
    files = sorted(glob.glob(f"{data_dir}/{prefix}_*.csv"))
    newest = files[-1] if files else None
    previous = files[-2] if len(files) > 1 else None
    return newest, previous


def check_manager(prefix: str, normalize, data_dir: str = "data",
                  today: date | None = None) -> list[Check]:
    newest, previous = latest_two(prefix, data_dir)
    if newest is None:
        return [Check(prefix, "file exists", False, "no CSV found")]

    raw = pd.read_csv(newest)
    manager = raw["manager"].iloc[0] if len(raw) else prefix
    checks: list[Check] = []

    # 0. Freshness: is the newest scrape recent? (file names end in _YYYY-MM-DD.csv)
    scraped = date.fromisoformat(Path(newest).stem.rsplit("_", 1)[1])
    age = ((today or date.today()) - scraped).days
    checks.append(Check(manager, "recent", age <= MAX_AGE_DAYS, f"newest scrape {scraped} ({age} days old)"))

    # 1. Volume: did the scrape return anything, and not far fewer rows than last time?
    checks.append(Check(manager, "has rows", len(raw) > 0, f"{len(raw)} rows"))
    if previous is not None:
        prev_n = len(pd.read_csv(previous))
        drop = 1 - len(raw) / prev_n if prev_n else 0
        checks.append(Check(manager, "row count stable", drop <= MAX_COUNT_DROP,
                            f"{prev_n} -> {len(raw)} rows ({drop:+.0%} drop)"))

    # 2. Schema: can it be converted to the site's common columns?
    try:
        df = normalize(raw)
    except KeyError as e:
        checks.append(Check(manager, "schema", False, f"missing column {e}"))
        return checks
    checks.append(Check(manager, "schema", list(df.columns) == COLUMNS, "common columns present"))

    if df.empty:
        return checks

    # 3. Completeness: share of rows with a usable price and a name.
    missing_price = df["rent_per_bed_min"].isna().mean()
    checks.append(Check(manager, "prices present", missing_price <= MAX_MISSING_PRICE,
                        f"{missing_price:.0%} missing"))
    checks.append(Check(manager, "names present", df["name"].notna().all(),
                        f"{df['name'].isna().sum()} missing"))

    # 4. Validity: prices in a believable range, min <= max.
    lo, hi = RENT_PER_BED_RANGE
    priced = df.dropna(subset=["rent_per_bed_min"])
    out_of_range = priced[(priced["rent_per_bed_min"] < lo) | (priced["rent_per_bed_max"] > hi)]
    checks.append(Check(manager, "prices in range", out_of_range.empty,
                        f"{len(out_of_range)} outside ${lo}-${hi}/bed"))
    inverted = priced[priced["rent_per_bed_min"] > priced["rent_per_bed_max"]]
    checks.append(Check(manager, "min <= max", inverted.empty, f"{len(inverted)} inverted ranges"))

    # 5. Uniqueness: one row per listing.
    dupes = raw["external_id"].duplicated().sum() if "external_id" in raw else 0
    checks.append(Check(manager, "no duplicate listings", dupes == 0, f"{dupes} duplicates"))
    return checks


def run(data_dir: str = "data") -> list[Check]:
    results: list[Check] = []
    for prefix, normalize in SOURCES.items():
        if prefix in PAUSED:
            results.append(Check(prefix, "source active", True, PAUSED[prefix], skipped=True))
            continue
        results.extend(check_manager(prefix, normalize, data_dir))
    return results


def report(results: list[Check]) -> str:
    lines = ["| Manager | Check | Result | Detail |", "|---|---|---|---|"]
    for c in results:
        status = "SKIP" if c.skipped else ("PASS" if c.passed else "FAIL")
        lines.append(f"| {c.manager} | {c.name} | {status} | {c.detail} |")
    failed = sum(not c.passed for c in results)
    skipped = sum(c.skipped for c in results)
    lines.append(f"\n**{len(results) - failed - skipped} passed, {failed} failed, {skipped} skipped**")
    return "\n".join(lines)


def main() -> None:
    results = run()
    text = report(results)
    print(text)
    summary = os.getenv("GITHUB_STEP_SUMMARY")  # set automatically inside GitHub Actions
    if summary:
        with open(summary, "a") as f:
            f.write("## Data quality\n\n" + text + "\n")
    sys.exit(1 if any(not c.passed for c in results) else 0)


if __name__ == "__main__":
    main()
