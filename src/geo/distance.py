"""Distance from a listing to the UIUC Main Quad."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

# Approximate center of the Main Quad (between the Illini Union and Foellinger).
QUAD_LAT, QUAD_LON = 40.1075, -88.2272
EARTH_RADIUS_MI = 3958.8


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line ("as the crow flies") distance in miles between two points."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))


def dist_to_quad_mi(lat: float | None, lon: float | None) -> float | None:
    """Miles from (lat, lon) to the Main Quad; None if the location is unknown."""
    if lat is None or lon is None:
        return None
    return round(haversine_mi(lat, lon, QUAD_LAT, QUAD_LON), 3)