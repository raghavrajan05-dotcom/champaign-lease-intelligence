"""Build a small analytics warehouse (DuckDB) from every day of scraped data.

Usage:
    python -m src.warehouse

Reads ALL CSVs in data/ (every manager, every day), converts each to the
common columns, and loads a star schema into warehouse/lease.duckdb:

    dim_manager        one row per property manager
    dim_property       one row per building/address, with location and distance
    fct_listing_daily  one row per listing per day  (the "grain")

plus analysis views (v_daily_summary, v_price_changes, v_delisted).
The file is rebuilt from scratch each run, so it always matches data/.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import duckdb
import pandas as pd

from src.geo.geocode import attach_distance, load_cache
from src.normalize import SOURCES

DB_PATH = Path("warehouse/lease.duckdb")
DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.csv$")
LISTING_TYPE = {
    "JSM Living": "Unit type",
    "Community Property Management": "Single unit",
}


def load_history(data_dir: str = "data") -> pd.DataFrame:
    """Every scraped file for every manager, stacked, with a snapshot_date column."""
    frames = []
    for prefix, normalize in SOURCES.items():
        for path in sorted(glob.glob(f"{data_dir}/{prefix}_*.csv")):
            raw = pd.read_csv(path)
            if raw.empty:
                continue
            df = normalize(raw)
            df["snapshot_date"] = pd.to_datetime(DATE_RE.search(path).group(1)).date()
            frames.append(df)
    if not frames:
        raise SystemExit(f"No scraped CSVs found in {data_dir}/")
    return pd.concat(frames, ignore_index=True)


SCHEMA_SQL = """
CREATE TABLE dim_manager AS
SELECT ROW_NUMBER() OVER (ORDER BY manager) AS manager_id,
       manager AS manager_name,
       listing_type
FROM (SELECT DISTINCT manager, listing_type FROM staged);

CREATE TABLE dim_property AS
SELECT ROW_NUMBER() OVER (ORDER BY m.manager_id, s.name) AS property_id,
       m.manager_id, s.name, s.lat AS latitude, s.lon AS longitude, s.miles_to_quad,
       CASE WHEN s.miles_to_quad IS NULL THEN 'Unknown'
            WHEN s.miles_to_quad < 0.5 THEN 'Under 0.5 mi'
            WHEN s.miles_to_quad < 1.0 THEN '0.5-1 mi'
            WHEN s.miles_to_quad < 2.0 THEN '1-2 mi'
            ELSE '2+ mi' END AS distance_band
FROM (SELECT DISTINCT manager, name, lat, lon, miles_to_quad FROM staged) s
JOIN dim_manager m ON m.manager_name = s.manager;

-- Grain: one row per listing (url) per snapshot day. Same-day duplicates are dropped.
CREATE TABLE fct_listing_daily AS
SELECT DISTINCT ON (s.url, s.snapshot_date)
       s.snapshot_date, s.url AS listing_key, p.property_id, m.manager_id,
       s.beds_min AS beds, s.rent_per_bed_min, s.rent_per_bed_max,
       (s.rent_per_bed_min + s.rent_per_bed_max) / 2 AS rent_per_bed_mid,
       s.available
FROM staged s
JOIN dim_manager m ON m.manager_name = s.manager
JOIN dim_property p ON p.manager_id = m.manager_id AND p.name = s.name
ORDER BY s.url, s.snapshot_date;

-- How much data per manager per day, and what it costs.
CREATE VIEW v_daily_summary AS
SELECT f.snapshot_date, m.manager_name,
       COUNT(*) AS listings,
       MEDIAN(f.rent_per_bed_mid) AS median_rent_per_bed
FROM fct_listing_daily f JOIN dim_manager m USING (manager_id)
GROUP BY ALL ORDER BY f.snapshot_date, m.manager_name;

-- Listings whose price changed since their previous snapshot.
CREATE VIEW v_price_changes AS
SELECT * FROM (
    SELECT f.listing_key, p.name, m.manager_name, f.snapshot_date,
           LAG(f.rent_per_bed_mid) OVER w AS prev_rent_per_bed,
           f.rent_per_bed_mid AS rent_per_bed
    FROM fct_listing_daily f
    JOIN dim_property p USING (property_id)
    JOIN dim_manager m ON m.manager_id = f.manager_id
    WINDOW w AS (PARTITION BY f.listing_key ORDER BY f.snapshot_date)
) WHERE prev_rent_per_bed IS NOT NULL AND rent_per_bed <> prev_rent_per_bed;

-- Listings seen before but missing from their manager's latest snapshot
-- (a rough signal a unit was leased; unreliable on days a scraper failed).
CREATE VIEW v_delisted AS
WITH latest AS (
    SELECT manager_id, MAX(snapshot_date) AS latest_date
    FROM fct_listing_daily GROUP BY manager_id
)
SELECT f.listing_key, p.name, m.manager_name,
       MIN(f.snapshot_date) AS first_seen, MAX(f.snapshot_date) AS last_seen,
       COUNT(*) AS days_seen
FROM fct_listing_daily f
JOIN latest l USING (manager_id)
JOIN dim_property p USING (property_id)
JOIN dim_manager m ON m.manager_id = f.manager_id
GROUP BY f.listing_key, p.name, m.manager_name, l.latest_date
HAVING MAX(f.snapshot_date) < l.latest_date;
"""


def build(data_dir: str = "data", db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    history = load_history(data_dir)
    staged = attach_distance(history, load_cache())
    staged["listing_type"] = staged["manager"].map(LISTING_TYPE).fillna("Other")

    db_path.parent.mkdir(exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # rebuild from scratch: data/ is the source of truth
    con = duckdb.connect(str(db_path))
    con.register("staged", staged)
    con.execute(SCHEMA_SQL)
    con.unregister("staged")
    return con


def main() -> None:
    con = build()
    for table in ("dim_manager", "dim_property", "fct_listing_daily"):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:<20} {n:>6} rows")
    days = con.execute("SELECT COUNT(DISTINCT snapshot_date) FROM fct_listing_daily").fetchone()[0]
    print(f"{'days of history':<20} {days:>6}")
    print("\nLatest day per manager:")
    print(con.execute("""
        SELECT * FROM v_daily_summary
        QUALIFY snapshot_date = MAX(snapshot_date) OVER (PARTITION BY manager_name)
    """).df().to_string(index=False))
    print(f"\nprice changes: {con.execute('SELECT COUNT(*) FROM v_price_changes').fetchone()[0]}"
          f" | delisted: {con.execute('SELECT COUNT(*) FROM v_delisted').fetchone()[0]}")
    con.close()


if __name__ == "__main__":
    main()
