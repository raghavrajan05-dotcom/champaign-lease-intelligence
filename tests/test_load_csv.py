"""Integration test: needs the Postgres container running (docker compose up -d)."""

import csv

import psycopg
import pytest

from src.db.load_csv import DATABASE_URL, load_csv

MANAGER = "TEST MANAGER (pytest)"
COLS = ["manager", "external_id", "scraped_on", "title", "address", "rent",
        "price_basis", "beds", "baths", "sqft", "available_date", "available_raw", "url"]


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres not running; start it with: docker compose up -d")
    yield c
    with c.transaction(), c.cursor() as cur:  # remove test rows
        cur.execute("SELECT id FROM managers WHERE name = %s", (MANAGER,))
        row = cur.fetchone()
        if row:
            mid = row[0]
            cur.execute("DELETE FROM listing_snapshots WHERE run_id IN "
                        "(SELECT id FROM scrape_runs WHERE manager_id = %s)", (mid,))
            cur.execute("DELETE FROM scrape_runs WHERE manager_id = %s", (mid,))
            cur.execute("DELETE FROM properties WHERE manager_id = %s", (mid,))
            cur.execute("DELETE FROM managers WHERE id = %s", (mid,))
    c.close()


def test_load_is_idempotent(conn, tmp_path):
    path = tmp_path / "sample.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerow({"manager": MANAGER, "external_id": "test-1", "scraped_on": "2026-10-27",
                    "address": "1 Test St, Champaign, IL 61820", "rent": "1250.0",
                    "price_basis": "per_unit", "beds": "2", "baths": "1.5", "sqft": "800",
                    "available_date": "2027-01-15"})
        w.writerow({"manager": MANAGER, "external_id": "test-2", "scraped_on": "2026-10-27",
                    "address": "", "rent": "900"})

    first = load_csv(path, conn)
    second = load_csv(path, conn)

    assert first == {"read": 2, "inserted": 1, "skipped_no_address": 1}
    assert second["inserted"] == 0  # same listing, same day: not duplicated