from src.scrapers import floorplans

OCTAVE = """
<div class="jet-portfolio__content-inner"><h3 class="jet-portfolio__title">A1</h3>
<p class="jet-portfolio__desc">1 Bed / 1 Bath<br/>547 SQ FT<br/><b>$1,869</b><br/>
<span class="floor-remaining"></span></p></div>
<div class="jet-portfolio__content-inner"><h3 class="jet-portfolio__title">D1</h3>
<p class="jet-portfolio__desc">4 Bed / 4 Bath<br/>1,423 SQ FT<br/><b>$1,089</b><br/>
<span class="floor-remaining">Sold Out</span></p></div>
"""


def test_octave_plans():
    a, d = floorplans.parse_octave(OCTAVE, floorplans.BUILDINGS["octave"])
    assert (a["beds"], a["baths"], a["rent_per_bed_min"], a["status"]) == (1, 1.0, 1869, "Available")
    assert (d["status"], d["rent_per_bed_min"]) == ("Sold out", None)
