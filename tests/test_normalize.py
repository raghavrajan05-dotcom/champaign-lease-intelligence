import pandas as pd

from src.normalize import COLUMNS, from_appfolio, from_greenstreet


def test_appfolio_splits_unit_rent_by_beds():
    df = pd.DataFrame({
        "manager": ["CPM"] * 3,
        "address": ["2BR place", "Studio place", None],
        "title": ["t1", "t2", "Unknown beds"],
        "rent": [1800.0, 700.0, 900.0],
        "beds": [2, 0, None],
        "available_raw": ["NOW", "1/15/27", None],
        "url": ["u1", "u2", "u3"],
        "scraped_on": ["2026-11-06"] * 3,
    })
    out = from_appfolio(df)
    assert list(out.columns) == COLUMNS
    assert out["rent_per_bed_min"].tolist()[:2] == [900.0, 700.0]  # studio = 1 bed
    assert pd.isna(out["rent_per_bed_min"].iloc[2])  # unknown beds: no per-bed price
    assert out["name"].iloc[2] == "Unknown beds"  # falls back to title


def test_greenstreet_keeps_ranges():
    df = pd.DataFrame({
        "manager": ["GSR"], "external_id": ["a"], "scraped_on": ["2026-11-06"],
        "name": ["105 E Armory Ave"], "rent_per_bed_min": [800.0],
        "rent_per_bed_max": [1150.0], "rent_per_unit_min": [1800.0],
        "rent_per_unit_max": [4200.0], "beds_min": [1], "beds_max": [4],
        "baths_min": [1.0], "baths_max": [4.0], "available_raw": ["Now"], "url": ["u"],
    })
    out = from_greenstreet(df)
    assert list(out.columns) == COLUMNS
    assert out.iloc[0]["available"] == "Now"
    assert (out.iloc[0]["rent_per_bed_min"], out.iloc[0]["rent_per_bed_max"]) == (800.0, 1150.0)