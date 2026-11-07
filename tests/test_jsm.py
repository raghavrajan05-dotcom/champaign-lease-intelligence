from datetime import date

from src.scrapers.jsm import parse_range, parse_units

TODAY = date(2026, 11, 7)

# Trimmed copy of JSM's real card markup (Nov 2026).
CARD = """
<li><article class="unit-card unit card">
  <div class="unit__card-photos">
    <h3 class="field--label sr-only">Image</h3>
    <h4><div class="field field--name-field-building"><a href="/node/130295">{name}</a></div></h4>
  </div>
  <div class="unit__card-content"><div class="unit__card-description">
    <div class="rent_combined rent"><div class="rent_label">RENT:</div><div class="rent_table">
      {pp}<div class="rent_unit">{unit}</div>
    </div></div>
    <div class="unit__card-stats">
      <div class="unit__card-bedrooms"><p>{beds}</p></div>
      <div class="unit__card-bathrooms"><p>{baths}</p></div>
    </div>
    <div class="unit__card-availability"><span>Available:</span> {avail}</div>
    <a class="call-to-action" href="{href}">View Listing</a>
  </div></div>
</article></li>
"""

SAMPLE = "<ul class='units-list'>" + CARD.format(
    name="601 S. Sixth - Campus Center",
    pp='<div class="rent_pp">$805.00 - $985.00/Person</div>',
    unit="$2415-2955/Unit", beds="3 Beds", baths="2 Bath",
    avail="Fall 2026, Spring 2027",
    href="/node/130295?bedrooms=3&amp;unittype=601S-3-2-B",
) + CARD.format(
    name="105 E. Green", pp="", unit="$1195/Unit", beds="Studio", baths="1 Bath",
    avail="Fall 2027", href="/node/1?bedrooms=0&amp;unittype=105G-0-1-A",
) + "</ul>"


def test_parse_range_formats():
    assert parse_range("$805.00 - $985.00/Person") == (805.0, 985.0)
    assert parse_range("$2415-2955/Unit") == (2415.0, 2955.0)
    assert parse_range("$1195/Unit") == (1195.0, 1195.0)
    assert parse_range("$0/Unit") == (None, None)
    assert parse_range(None) == (None, None)


def test_card_with_person_and_unit_prices():
    a = parse_units(SAMPLE, TODAY)[0]
    assert a["name"] == "601 S. Sixth - Campus Center"  # not the hidden "Image" label
    assert (a["rent_person_min"], a["rent_person_max"]) == (805.0, 985.0)
    assert (a["rent_unit_min"], a["rent_unit_max"]) == (2415.0, 2955.0)
    assert (a["beds"], a["baths"]) == (3, 2.0)
    assert a["terms"] == "Fall 2026; Spring 2027"
    assert a["url"] == "https://jsmliving.com/node/130295?bedrooms=3&unittype=601S-3-2-B"


def test_studio_with_unit_price_only():
    b = parse_units(SAMPLE, TODAY)[1]
    assert (b["beds"], b["baths"]) == (0, 1.0)
    assert b["rent_person_min"] is None
    assert (b["rent_unit_min"], b["rent_unit_max"]) == (1195.0, 1195.0)