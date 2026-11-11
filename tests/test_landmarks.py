import pandas as pd

from src.geo.landmarks import load_landmarks, miles_to, minutes


def test_rows_without_coordinates_are_left_out(tmp_path):
    path = tmp_path / "landmarks.csv"
    pd.DataFrame({"name": ["Quad", "Grainger"], "short": ["Quad", "Grainger"],
                  "address": ["", "1301 W Springfield Ave"], "lat": [40.1075, None],
                  "lon": [-88.2272, None], "source": ["x", ""]}).to_csv(path, index=False)
    assert load_landmarks(path)["name"].tolist() == ["Quad"]


def test_committed_landmarks_are_near_campus():
    lm = load_landmarks()
    assert "Main Quad" in set(lm["name"])
    assert (miles_to(lm, 40.1075, -88.2272) < 2).all()  # a typo'd coordinate would land far away


def test_miles_and_minutes():
    df = pd.DataFrame({"lat": [40.1075, None], "lon": [-88.2272, None]})
    miles = miles_to(df, 40.1075 + 1 / 69, -88.2272)  # 1/69 degree of latitude ~ 1 mile
    assert abs(miles[0] - 1.0) < 0.01 and pd.isna(miles[1])
    assert minutes(pd.Series([1.0]), 3.0)[0] == 26  # 1 mi x 1.3 detour at 3 mph
