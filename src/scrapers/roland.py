"""Roland Realty (Webflow site). Every unit, available or not, across ~14 pages.

Usage: python -m src.scrapers.roland
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.scrapers.common import get, money, save

MANAGER = "Roland Realty"
BASE = "https://www.roland-realty.com"
LIST_URL = BASE + "/for-rent/available-fall/all-unit-listings"
PAGE_PARAM = "f5630116_page"  # the site's own pagination parameter
MAX_PAGES = 40


def _field(card, name: str) -> str | None:
    el = card.select_one(f'[fs-cmsfilter-field="{name}"]')
    return el.get_text(strip=True) if el else None


def parse(html: str) -> list[dict]:
    rows = []
    for card in BeautifulSoup(html, "html.parser").select("a.link-block-unit-listing"):
        counts = card.find(string=re.compile(r"\d+\s+Bedrooms?|Studio", re.I)) or ""
        m = re.search(r"(\d+)\s+Bedrooms?", counts, re.I)
        beds = int(m.group(1)) if m else (0 if "studio" in counts.lower() else None)
        if beds is None and (s := _field(card, "bed-string")):
            beds = 0 if "studio" in s.lower() else int(re.search(r"\d+", s).group())
        unit = money(_field(card, "rent-fall"))
        per_bed = money(_field(card, "rent-fall-btb"))
        if per_bed is None and unit is not None:
            per_bed = round(unit / max(beds or 1, 1))
        available = (_field(card, "available") or "").lower() == "true"
        rows.append({
            "external_id": card["href"],
            "name": _field(card, "address") or _field(card, "name"),
            "beds": beds,
            "baths": money(_field(card, "bath")),
            "rent_per_bed_min": per_bed, "rent_per_bed_max": per_bed,
            "rent_unit": unit,
            "status": "Available" if available else "Unavailable",
            "available": "Fall" if available else None,
            "url": BASE + card["href"],
        })
    return rows


def main() -> None:
    pages, rows, seen = [], [], set()
    for n in range(1, MAX_PAGES + 1):
        html = get(LIST_URL, params={PAGE_PARAM: n}).text
        new = [r for r in parse(html) if r["external_id"] not in seen]
        if not new:
            break
        pages.append(html)
        seen.update(r["external_id"] for r in new)
        rows += new
    save(MANAGER, rows, "\n<!-- page break -->\n".join(pages))


if __name__ == "__main__":
    main()
