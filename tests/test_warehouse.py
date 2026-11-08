import pandas as pd

from src import warehouse

CPM_COLS = ["manager", "external_id", "scraped_on", "title", "address", "rent",
            "price_basis", "beds", "baths", "sqft", "available_date", "available_raw", "url"]


def cpm_day(tmp_path, day, units):
    rows = [["Community Property Management", uid, day, "t", addr, rent, "per_unit",
             beds, 1, None, None, "NOW", f"https://x/{uid}"]
            for uid, addr, rent, beds in units]
    pd.DataFrame(rows, columns=CPM_COLS).to_csv(
        tmp_path / f"community-property-management_{day}.csv", index=False)


def test_star_schema_grain_and_views(tmp_path, monkeypatch):
    monkeypatch.setattr(warehouse, "load_cache",
                        lambda: pd.DataFrame(columns=["name", "lat", "lon", "matched_address"]))
    cpm_day(tmp_path, "2026-11-06", [("a", "1 A St", 1800, 2), ("b", "2 B St", 900, 1)])
    cpm_day(tmp_path, "2026-11-07", [("a", "1 A St", 1700, 2)])  # a: price drop; b: gone

    con = warehouse.build(str(tmp_path), tmp_path / "w.duckdb")
    count = lambda sql: con.execute(sql).fetchone()[0]

    assert count("SELECT COUNT(*) FROM dim_manager") == 1
    assert count("SELECT COUNT(*) FROM dim_property") == 2
    assert count("SELECT COUNT(*) FROM fct_listing_daily") == 3  # one row per listing per day
    assert count("""SELECT COUNT(*) FROM (SELECT listing_key, snapshot_date
                    FROM fct_listing_daily GROUP BY ALL HAVING COUNT(*) > 1)""") == 0

    change = con.execute("SELECT prev_rent_per_bed, rent_per_bed FROM v_price_changes").fetchall()
    assert change == [(900.0, 850.0)]  # $1,800/2 beds -> $1,700/2 beds
    assert con.execute("SELECT listing_key FROM v_delisted").fetchall() == [("https://x/b",)]