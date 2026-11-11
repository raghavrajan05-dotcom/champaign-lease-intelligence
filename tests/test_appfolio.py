from datetime import date

from src.scrapers.appfolio import (
    parse_available, parse_bed_bath, parse_int, parse_listings, parse_money,
)

TODAY = date(2026, 10, 22)


def test_parse_money():
    assert parse_money("$1,250") == 1250.0
    assert parse_money(None) is None


def test_parse_int():
    assert parse_int("1,000") == 1000


def test_parse_bed_bath():
    assert parse_bed_bath("2 bd / 1.5 ba") == (2, 1.5)
    assert parse_bed_bath("1 bd") == (1, None)
    assert parse_bed_bath("Studio / 1 ba") == (0, 1.0)


def test_parse_available():
    assert parse_available("1/15/27", TODAY) == date(2027, 1, 15)
    assert parse_available("NOW", TODAY) == TODAY
    assert parse_available("soon", TODAY) is None


SAMPLE = """
<div class="listings">
  <div class="listing-item">
    <a href="/listings/detail/044bf5ef-22a6-40e4-8ed7-dfa0bf809e28">306-410 E Michigan</a>
    <dl><dt>RENT</dt><dd>$1,250</dd></dl>
    <dl><dt>Square Feet</dt><dd>800</dd></dl>
    <dl><dt>Bed / Bath</dt><dd>2 bd / 1.5 ba</dd></dl>
    <dl><dt>Available</dt><dd>1/15/27</dd></dl>
    <h2><a href="/listings/detail/044bf5ef-22a6-40e4-8ed7-dfa0bf809e28">Renovated 2BR</a></h2>
    <span class="js-listing-address">306-410 E Michigan, Urbana, IL 61801</span>
  </div>
  <div class="listing-item">
    <a href="/listings/detail/0901dc27-e6ee-4db7-83c3-772b935ee91d">217 S Neil St</a>
    <dl><dt>RENT</dt><dd>$1,745</dd></dl>
    <dl><dt>Bed / Bath</dt><dd>2 bd / 2 ba</dd></dl>
    <dl><dt>Available</dt><dd>NOW</dd></dl>
    <p>217 S Neil St, Champaign, IL 61820</p>
  </div>
</div>
"""


def test_parse_listings_keeps_listings_separate():
    rows = parse_listings(SAMPLE, "https://x.appfolio.com", "Test PM", TODAY)
    assert len(rows) == 2
    a, b = rows
    assert (a["rent"], a["beds"], a["baths"], a["sqft"]) == (1250.0, 2, 1.5, 800)
    assert a["address"] == "306-410 E Michigan, Urbana, IL 61801"
    assert a["available_date"] == "2027-01-15"
    assert b["rent"] == 1745.0 and b["available_date"] == "2026-10-22"
    assert b["address"] == "217 S Neil St, Champaign, IL 61820"


def test_keep_cities_drops_other_towns():
    from src.scrapers.appfolio import keep_cities

    rows = [{"address": "511 E White, Champaign, IL 61820"},
            {"address": "360 Olympic Ln, Decatur, IL 62526"},
            {"address": None}]
    assert keep_cities(rows, ["Champaign", "Urbana"]) == rows[:1]
    assert keep_cities(rows, None) == rows
