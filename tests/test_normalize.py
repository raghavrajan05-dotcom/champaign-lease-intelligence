import pandas as pd

from src.normalize import COLUMNS, from_appfolio


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


def test_jsm_prefers_listed_per_person_price():
    from src.normalize import from_jsm

    df = pd.DataFrame({
        "manager": ["JSM"] * 2, "name": ["601 S. Sixth - Campus Center", "707 S. Sixth"],
        "beds": [3, 2], "rent_unit_min": [2415.0, 1800.0], "rent_unit_max": [2955.0, 2000.0],
        "rent_person_min": [805.0, None], "rent_person_max": [985.0, None],
        "terms": ["Fall 2026", "Fall 2027"], "url": ["u1", "u2"],
        "scraped_on": ["2026-11-07"] * 2,
    })
    out = from_jsm(df)
    assert list(out.columns) == COLUMNS
    assert (out.loc[0, "rent_per_bed_min"], out.loc[0, "rent_per_bed_max"]) == (805.0, 985.0)
    assert (out.loc[1, "rent_per_bed_min"], out.loc[1, "rent_per_bed_max"]) == (900.0, 1000.0)


def test_load_latest_remote_skips_missing_managers(tmp_path):
    import pandas as pd
    from src.normalize import load_latest_remote

    (tmp_path / "latest").mkdir()
    pd.DataFrame({"manager": ["JSM Living"], "name": ["105 E. Green"], "beds": [0],
                  "rent_unit_min": [1195.0], "rent_unit_max": [1195.0],
                  "rent_person_min": [None], "rent_person_max": [None],
                  "terms": ["Fall 2027"], "url": ["u"], "scraped_on": ["2026-11-10"]}
                 ).to_csv(tmp_path / "latest" / "jsm-living.csv", index=False)
    out = load_latest_remote(base=tmp_path.as_uri())  # file:// stands in for GitHub
    assert list(out["manager"]) == ["JSM Living"]  # the other two files don't exist: skipped


def test_unpriced_buildings_have_no_prices(tmp_path):
    from src.normalize import load_unpriced_buildings

    path = tmp_path / "unpriced.csv"
    pd.DataFrame({"manager": ["Green Street Realty"], "name": ["105 E Armory Ave"],
                  "url": ["https://example.com/105"], "listed_as_of": ["2026-11-03"]}
                 ).to_csv(path, index=False)
    out = load_unpriced_buildings(path)
    assert list(out.columns) == COLUMNS
    assert out["rent_per_bed_min"].isna().all() and out["beds_min"].isna().all()
    assert out.loc[0, "url"] == "https://example.com/105"
