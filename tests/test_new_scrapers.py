"""Parsers for the newer managers, tested on small hand-made copies of each site's markup."""

import json

from src.scrapers import appfolio_feed, floorplans, mhm, roland
from src.scrapers.common import money

ROLAND = """
<a class="link-block-unit-listing" href="/unit-listings/36-e-chalmers-st">
  <div>6 Bedrooms 2 Bathrooms</div>
  <div fs-cmsfilter-field="name">36 E Chalmers St</div>
  <div fs-cmsfilter-field="bath">2</div>
  <div fs-cmsfilter-field="rent-fall">6342</div>
  <div fs-cmsfilter-field="rent-fall-btb">1057</div>
  <div fs-cmsfilter-field="available">false</div>
  <div fs-cmsfilter-field="address">36 E Chalmers St</div>
</a>
<a class="link-block-unit-listing" href="/unit-listings/909-s-first-st-8">
  <div>Studio / 1 Bathrooms</div>
  <div fs-cmsfilter-field="bed-string">Studio</div>
  <div fs-cmsfilter-field="rent-fall">920</div>
  <div fs-cmsfilter-field="available">true</div>
  <div fs-cmsfilter-field="address">909 S First St</div>
</a>
"""

MHM = """
<div class="propgridc"><a href="https://www.mhmproperties.com/property/303-s-fifth-street/">
  <h2>303 S. Fifth Street</h2><span>Price Per Person</span>
  <p class="ppricebox">1 Bed : LEASED!</p>
  <p class="ppricebox">2 Bed/2 Bath: From $1,105/Person</p>
  <p class="ppricebox">3 Bed/2 Bath - Loft : $1,155 (LAST UNIT!)</p>
</a></div>
"""


def test_money():
    assert money("$1,105/Person") == 1105 and money("8973") == 8973 and money(None) is None


def test_roland_units_and_status():
    a, b = roland.parse(ROLAND)
    assert (a["beds"], a["rent_unit"], a["rent_per_bed_min"], a["status"]) == (6, 6342, 1057, "Unavailable")
    assert (b["beds"], b["rent_per_bed_min"], b["status"]) == (0, 920, "Available")


def test_mhm_lines():
    leased, two, loft = mhm.parse(MHM)
    assert leased["status"] == "Leased" and leased["rent_per_bed_min"] is None
    assert (two["beds"], two["rent_per_bed_min"], two["status"]) == (2, 1105, "Available")
    assert (loft["rent_per_bed_min"], loft["status"]) == (1155, "Last unit")  # card says per person
    assert two["name"] == "303 S. Fifth Street (2 Bed/2 Bath)"


def test_seven07_sold_out():
    feed = json.dumps({"floorPlans": [
        {"name": "4BR/4BA", "bedroomCount": 4.0, "bathroomCount": 4.0, "marketRent": 1250,
         "unitsAvailable": 3},
        {"name": "Studio", "bedroomCount": 0.0, "bathroomCount": 1.0, "marketRent": 1720,
         "unitsAvailable": 0}]})
    a, b = floorplans.parse_seven07(feed, floorplans.BUILDINGS["seven07"])
    assert (a["beds"], a["rent_per_bed_min"], a["status"]) == (4, 1250, "Available")
    assert b["status"] == "Sold out"
    assert a["name"].startswith("707 S 4th St - Seven07")


def test_the_rive_uses_special_price():
    data = {"categories": {"Four Bedroom": {"floorplans": [
        {"name": "4x2 Balcony", "beds": "4", "baths": "2", "sold_out": False,
         "rates": [{"value": 1234, "special_value": 1119}]},
        {"name": "4x2 Corner", "beds": "4", "baths": "2", "sold_out": True,
         "rates": [{"value": "", "special_value": ""}]}]}}}
    html = f"<script>var localData = {{}};\nlocalData.apiTransitionData = {json.dumps(data)};</script>"
    a, b = floorplans.parse_the_rive(html, floorplans.BUILDINGS["the-rive"])
    assert (a["rent_per_bed_min"], a["status"]) == (1119, "Available")
    assert (b["rent_per_bed_min"], b["status"]) == (None, "Sold out")


def test_smile_per_person_and_city_filter():
    base = {"listable_uid": "u1", "database_url": "https://fairlawn.appfolio.com/",
            "bathrooms": 1.0, "available": True, "available_date": "2027-08-17",
            "marketing_description": ""}
    rows = appfolio_feed.parse([
        {**base, "full_address": "809 W Springfield, Urbana, IL 61801", "bedrooms": 4,
         "market_rent": 399.0, "marketing_title": "Individual Leasing Available!"},
        {**base, "listable_uid": "u2", "full_address": "1 Main St, Champaign, IL 61820",
         "bedrooms": 2, "market_rent": 1400.0, "marketing_title": "Two bed apartment"},
        {**base, "listable_uid": "u3", "full_address": "360 Olympic Ln, Decatur, IL 62526",
         "bedrooms": 2, "market_rent": 932.0, "marketing_title": "x"},
    ])
    assert [r["rent_per_bed_min"] for r in rows] == [399.0, 700]  # per person; whole unit split
    assert rows[0]["url"] == "https://fairlawn.appfolio.com/listings/detail/u1"
