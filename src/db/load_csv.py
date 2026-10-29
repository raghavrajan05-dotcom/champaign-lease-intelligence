"""Load one scraper CSV into Postgres.

Usage:
    python -m src.db.load_csv data/community-property-management_2026-10-27.csv

Safe to re-run: a listing already saved for the same day is skipped.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import psycopg

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://lease:lease@localhost:5433/leases"
)


def _num(v: str | None, cast=float):
    return cast(float(v)) if v not in (None, "") else None


def _txt(v: str | None):
    return v if v not in (None, "") else None


def load_csv(path: Path, conn: psycopg.Connection) -> dict:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {"read": 0, "inserted": 0, "skipped_no_address": 0}

    manager = rows[0]["manager"]
    inserted = skipped = 0
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """INSERT INTO managers (name) VALUES (%s)
               ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
               RETURNING id""",
            (manager,),
        )
        manager_id = cur.fetchone()[0]

        cur.execute(
            """INSERT INTO scrape_runs (manager_id, status)
               VALUES (%s, 'running') RETURNING id""",
            (manager_id,),
        )
        run_id = cur.fetchone()[0]

        for r in rows:
            address = _txt(r["address"])
            if address is None:
                skipped += 1
                continue
            cur.execute(
                """INSERT INTO properties (manager_id, address) VALUES (%s, %s)
                   ON CONFLICT (manager_id, address)
                   DO UPDATE SET address = EXCLUDED.address
                   RETURNING id""",
                (manager_id, address),
            )
            property_id = cur.fetchone()[0]

            cur.execute(
                """INSERT INTO listing_snapshots
                   (run_id, property_id, external_id, scraped_on, rent, price_basis,
                    beds, baths, sqft, available_date, url)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (external_id, scraped_on) DO NOTHING""",
                (
                    run_id, property_id, r["external_id"], r["scraped_on"],
                    _num(r["rent"]), _txt(r["price_basis"]),
                    _num(r["beds"], int), _num(r["baths"]), _num(r["sqft"], int),
                    _txt(r["available_date"]), _txt(r["url"]),
                ),
            )
            inserted += cur.rowcount

        cur.execute(
            """UPDATE scrape_runs
               SET status = 'success', finished_at = now(), n_listings = %s
               WHERE id = %s""",
            (inserted, run_id),
        )
    return {"read": len(rows), "inserted": inserted, "skipped_no_address": skipped}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", type=Path)
    args = ap.parse_args()
    with psycopg.connect(DATABASE_URL) as conn:
        stats = load_csv(args.csv_path, conn)
    print(
        f"read {stats['read']}, inserted {stats['inserted']}, "
        f"skipped (no address) {stats['skipped_no_address']}"
    )


if __name__ == "__main__":
    main()