import pandas as pd

from src.normalize import from_greenstreet
from src.quality import check_manager

GS_COLS = ["manager", "external_id", "scraped_on", "name", "rent_per_bed_min",
           "rent_per_bed_max", "rent_per_unit_min", "rent_per_unit_max", "beds_min",
           "beds_max", "baths_min", "baths_max", "available_raw", "url"]


def write(tmp_path, day, rows):
    df = pd.DataFrame(rows, columns=GS_COLS)
    df.to_csv(tmp_path / f"green-street-realty_{day}.csv", index=False)


def row(i, lo=800, hi=1000, name="Bldg"):
    return ["Green Street Realty", f"id{i}", "2026-11-08", f"{name} {i}", lo, hi,
            None, None, 1, 2, 1, 1, "Now", "u"]


def results(tmp_path):
    checks = check_manager("green-street-realty", from_greenstreet, str(tmp_path))
    return {c.name: c.passed for c in checks}


def test_healthy_day_passes(tmp_path):
    write(tmp_path, "2026-11-07", [row(i) for i in range(10)])
    write(tmp_path, "2026-11-08", [row(i) for i in range(9)])
    assert all(results(tmp_path).values())


def test_big_drop_in_listings_fails(tmp_path):
    write(tmp_path, "2026-11-07", [row(i) for i in range(10)])
    write(tmp_path, "2026-11-08", [row(i) for i in range(3)])
    assert results(tmp_path)["row count stable"] is False


def test_bad_prices_fail(tmp_path):
    write(tmp_path, "2026-11-08", [row(0, lo=5, hi=10), row(1, lo=1200, hi=900), row(2)])
    r = results(tmp_path)
    assert r["prices in range"] is False
    assert r["min <= max"] is False


def test_missing_prices_and_duplicates_fail(tmp_path):
    rows = [row(i, lo=None, hi=None) for i in range(5)] + [row(0)]
    write(tmp_path, "2026-11-08", rows)
    r = results(tmp_path)
    assert r["prices present"] is False
    assert r["no duplicate listings"] is False


def test_no_file_fails(tmp_path):
    assert results(tmp_path) == {"file exists": False}



def test_paused_source_is_skipped_not_failed(tmp_path, monkeypatch):
    from src import quality

    monkeypatch.setattr(quality, "PAUSED", {"green-street-realty": "paused for test"})
    results = quality.run(str(tmp_path))  # no Green Street file at all
    gs = [c for c in results if c.manager == "green-street-realty"]
    assert len(gs) == 1 and gs[0].skipped and gs[0].passed
    assert "1 skipped" in quality.report(results)