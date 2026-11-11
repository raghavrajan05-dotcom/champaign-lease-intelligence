import pandas as pd

from src.geo.geocode import (
    attach_distance, candidates, clean_address, geocode, street_variants,
)


def test_clean_address():
    assert clean_address("122 W. Hill St.") == "122 W Hill St"
    assert clean_address("306-410 E Michigan, Urbana, IL 61801") == "306 E Michigan, Urbana, IL 61801"
    assert clean_address("601 S. Sixth - Campus Center") == "601 S Sixth"


def test_street_variants_for_missing_suffix_and_ordinals():
    assert street_variants("601 S Sixth") == [
        "601 S Sixth", "601 S 6th", "601 S Sixth St", "601 S 6th St"]
    assert street_variants("105 E Armory Ave") == ["105 E Armory Ave"]
    assert street_variants("217 S Neil St, Champaign, IL 61820") == [
        "217 S Neil St, Champaign, IL 61820"]


def test_suffixless_address_tries_st_before_urbana():
    assert candidates("105 E. Green") == [
        "105 E Green, Champaign, IL", "105 E Green St, Champaign, IL",
        "105 E Green, Urbana, IL", "105 E Green St, Urbana, IL"]


def test_candidates_add_city_only_when_missing():
    assert candidates("105 E Armory Ave") == [
        "105 E Armory Ave, Champaign, IL", "105 E Armory Ave, Urbana, IL"]
    assert candidates("217 S Neil St, Champaign, IL 61820") == ["217 S Neil St, Champaign, IL 61820"]


class FakeSession:
    """Stands in for the Census API: answers from a dict, no network."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, params, timeout):
        self.calls.append(params["address"])
        hit = self.answers.get(params["address"])
        matches = [] if hit is None else [
            {"coordinates": {"y": hit[0], "x": hit[1]}, "matchedAddress": params["address"].upper()}]

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"result": {"addressMatches": matches}}

        return Resp()


def test_geocode_falls_back_to_urbana():
    s = FakeSession({"9 Fake St, Urbana, IL": (40.11, -88.21)})
    row = geocode("9 Fake St", s)
    assert s.calls == ["9 Fake St, Champaign, IL", "9 Fake St, Urbana, IL"]
    assert (row["lat"], row["lon"]) == (40.11, -88.21)


def test_geocode_rejects_far_away_match():
    s = FakeSession({"1 Main St, Champaign, IL": (41.88, -87.63)})  # Chicago
    assert geocode("1 Main St", s)["lat"] is None


def test_attach_distance():
    listings = pd.DataFrame({"name": ["A", "B"]})
    cache = pd.DataFrame({"name": ["A"], "lat": [40.1075], "lon": [-88.2272],
                          "matched_address": ["x"]})
    out = attach_distance(listings, cache)
    assert out.loc[0, "miles_to_quad"] == 0
    assert pd.isna(out.loc[1, "miles_to_quad"])
