import pytest

from src.geo.distance import QUAD_LAT, QUAD_LON, dist_to_quad_mi, haversine_mi


def test_same_point_is_zero():
    assert haversine_mi(QUAD_LAT, QUAD_LON, QUAD_LAT, QUAD_LON) == 0


def test_one_degree_latitude_is_about_69_miles():
    assert haversine_mi(40.0, -88.0, 41.0, -88.0) == pytest.approx(69.1, abs=0.1)


def test_distance_is_symmetric():
    a = haversine_mi(40.11, -88.24, 40.10, -88.22)
    b = haversine_mi(40.10, -88.22, 40.11, -88.24)
    assert a == pytest.approx(b)


def test_missing_location_returns_none():
    assert dist_to_quad_mi(None, -88.2) is None