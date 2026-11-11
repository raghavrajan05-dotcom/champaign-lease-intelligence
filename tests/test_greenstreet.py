from datetime import date

from src.scrapers.greenstreet import parse_properties

TODAY = date(2026, 11, 3)

SAMPLE = """
<div class="results">
  <div class="card">
    <a href="/properties/profile/105-e-armory-ave"><img src="x.jpg"></a>
    <h3>105 E Armory Ave</h3>
    <span>Available Now</span>
    <p>$800 - $1,150 /bed</p>
    <p>$1,800 - $4,200 /mth</p>
    <p>1-4 Bed</p><p>1-4 Bath</p>
    <a href="/properties/profile/105-e-armory-ave">View Availability</a>
  </div>
  <div class="card">
    <a href="/properties/profile/27-e-taylor-st">View Availability</a>
    <h3>27 E Taylor St</h3>
    <span>Available August 2026</span>
    <p>$1,450 /bed</p><p>$1,450 /mth</p>
    <p>1 Bed</p><p>1 Bath</p>
  </div>
  <div class="card">
    <a href="/properties/profile/905-e-oak-st">View Availability</a>
    <h3>905 E. Oak St.</h3>
    <p>$0 /bed</p><p>$1,425 - $1,959 /mth</p>
    <p>5+ Beds</p><p>1-2 Baths</p>
  </div>
</div>
"""


def test_parses_each_property_separately():
    rows = parse_properties(SAMPLE, TODAY)
    assert [r["external_id"] for r in rows] == [
        "105-e-armory-ave", "27-e-taylor-st", "905-e-oak-st"]


def test_price_and_size_ranges():
    a = parse_properties(SAMPLE, TODAY)[0]
    assert (a["rent_per_bed_min"], a["rent_per_bed_max"]) == (800, 1150)
    assert (a["rent_per_unit_min"], a["rent_per_unit_max"]) == (1800, 4200)
    assert (a["beds_min"], a["beds_max"]) == (1, 4)
    assert (a["baths_min"], a["baths_max"]) == (1, 4)
    assert a["available_raw"] == "Now"
    assert a["name"] == "105 E Armory Ave"


def test_single_values_and_month_availability():
    b = parse_properties(SAMPLE, TODAY)[1]
    assert (b["rent_per_bed_min"], b["rent_per_bed_max"]) == (1450, 1450)
    assert (b["beds_min"], b["beds_max"]) == (1, 1)
    assert b["available_raw"] == "August 2026"


def test_placeholder_price_and_open_ended_beds():
    c = parse_properties(SAMPLE, TODAY)[2]
    assert c["rent_per_bed_min"] is None  # "$0 /bed" is a placeholder
    assert (c["rent_per_unit_min"], c["rent_per_unit_max"]) == (1425, 1959)
    assert (c["beds_min"], c["beds_max"]) == (5, None)  # "5+": top unknown
    assert (c["baths_min"], c["baths_max"]) == (1, 2)