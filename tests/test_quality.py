import pandas as pd

from src.normalize import from_jsm
from src.quality import check_manager

JSM_COLS = ["manager", "external_id", "scraped_on", "name", "beds", "baths",
            "rent_unit_min", "rent_unit_max", "rent_person_min", "rent_person_max",
            "terms", "url"]


def write(tmp_path, day, rows):
    df = pd.DataFrame(rows, columns=JSM_COLS)
    df.to_csv(tmp_path / f"jsm-living_{day}.csv", index=False)


def row(i, lo=800, hi=1000, name="Bldg"):
    """One JSM unit type with a per-person price range lo-hi."""
    unit = lambda v: None if v is None else v * 2
    return ["JSM Living", f"id{i}", "2026-11-10", f"{name} {i}", 2, 1,
            unit(lo), unit(hi), lo, hi, "Fall 2027", "u"]


def results(tmp_path):
    checks = check_manager("jsm-living", from_jsm, str(tmp_path))
    return {c.name: c.passed for c in checks}


def test_healthy_day_passes(tmp_path):
    write(tmp_path, "2026-11-09", [row(i) for i in range(10)])
    write(tmp_path, "2026-11-10", [row(i) for i in range(9)])
    assert all(results(tmp_path).values())


def test_big_drop_in_listings_fails(tmp_path):
    write(tmp_path, "2026-11-09", [row(i) for i in range(10)])
    write(tmp_path, "2026-11-10", [row(i) for i in range(3)])
    assert results(tmp_path)["row count stable"] is False


def test_bad_prices_fail(tmp_path):
    write(tmp_path, "2026-11-10", [row(0, lo=5, hi=10), row(1, lo=1200, hi=900), row(2)])
    r = results(tmp_path)
    assert r["prices in range"] is False
    assert r["min <= max"] is False


def test_missing_prices_and_duplicates_fail(tmp_path):
    rows = [row(i, lo=None, hi=None) for i in range(5)] + [row(0)]
    write(tmp_path, "2026-11-10", rows)
    r = results(tmp_path)
    assert r["prices present"] is False
    assert r["no duplicate listings"] is False


def test_no_file_fails(tmp_path):
    assert results(tmp_path) == {"file exists": False}


def test_paused_source_is_skipped_not_failed(tmp_path, monkeypatch):
    from src import quality

    monkeypatch.setattr(quality, "PAUSED", {"jsm-living": "paused for test"})
    results_ = quality.run(str(tmp_path))  # no JSM file at all
    jsm = [c for c in results_ if c.manager == "jsm-living"]
    assert len(jsm) == 1 and jsm[0].skipped and jsm[0].passed
    assert "1 skipped" in quality.report(results_)
