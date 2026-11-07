"""Scrape JSM Living's available units.

Usage:
    python -m src.scrapers.jsm

Each <article class="unit-card"> on JSM's search page is one unit type at one
building, e.g. "601 S. Sixth - Campus Center", 3 Beds, 2 Bath,
"$805.00 - $985.00/Person", "$2415-2955/Unit", "Available: Fall 2026, Spring 2027".
Only buildings with units currently available appear. Writes one row per card
to data/ and saves the raw HTML to raw/ (both gitignored).
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://jsmliving.com"
SEARCH_URL = f"{BASE_URL}/search-available-units"
MANAGER = "JSM Living"
USER_AGENT = os.getenv(
    "USER_AGENT", "ChampaignLeaseIntel/0.1 (student research project)"
)
MIN_REAL_RENT = 100

MONEY_RANGE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)(?:\s*[-–]\s*\$?\s*([\d,]+(?:\.\d+)?))?")
BEDS_RE = re.compile(r"(\d+)\s*(?:bed(?:room)?s?|br)\b", re.I)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?|ba)\b", re.I)
TERM_RE = re.compile(r"\b(Fall|Spring|Summer)\s+(20\d\d)\b", re.I)

FIELDS = [
    "manager", "external_id", "scraped_on", "name", "beds", "baths",
    "rent_unit_min", "rent_unit_max", "rent_person_min", "rent_person_max",
    "terms", "url",
]


def _money(s: str | None) -> float | None:
    if not s:
        return None
    v = float(s.replace(",", ""))
    return v if v >= MIN_REAL_RENT else None


def parse_range(text: str | None) -> tuple[float | None, float | None]:
    """'$805.00 - $985.00/Person' -> (805, 985); '$2415-2955/Unit' -> (2415, 2955)"""
    m = MONEY_RANGE_RE.search(text or "")
    if not m:
        return None, None
    lo = _money(m.group(1))
    hi = _money(m.group(2)) if m.group(2) else lo
    return (lo, hi) if lo is not None else (None, None)


def parse_beds(text: str | None) -> int | None:
    if not text:
        return None
    if re.search(r"\bstudio\b", text, re.I):
        return 0
    m = BEDS_RE.search(text)
    return int(m.group(1)) if m else None


def _text(card: Tag, selector: str) -> str | None:
    el = card.select_one(selector)
    return el.get_text(" ", strip=True) if el else None


def parse_units(html: str, today: date) -> list[dict]:
    """One row per unit card (`<article class="unit-card">` on JSM's search page)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for card in soup.select("article.unit-card"):
        link = card.select_one("a.call-to-action") or card.select_one("a[href*='bedrooms=']")
        if link is None:
            continue
        href = link["href"]
        person_lo, person_hi = parse_range(_text(card, ".rent_pp"))
        unit_lo, unit_hi = parse_range(_text(card, ".rent_unit"))
        baths = BATHS_RE.search(_text(card, ".unit__card-bathrooms") or "")
        avail = _text(card, ".unit__card-availability") or ""
        terms = sorted({f"{s.title()} {y}" for s, y in TERM_RE.findall(avail)},
                       key=lambda t: (t.split()[1], t))
        rows.append({
            "manager": MANAGER,
            "external_id": href,
            "scraped_on": today.isoformat(),
            "name": _text(card, ".field--name-field-building"),
            "beds": parse_beds(_text(card, ".unit__card-bedrooms")),
            "baths": float(baths.group(1)) if baths else None,
            "rent_unit_min": unit_lo, "rent_unit_max": unit_hi,
            "rent_person_min": person_lo, "rent_person_max": person_hi,
            "terms": "; ".join(terms) or None,
            "url": urljoin(BASE_URL, href),
        })
    return rows


def main() -> None:
    today = date.today()
    resp = requests.get(SEARCH_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    html = resp.text

    raw_dir, data_dir = Path("raw"), Path("data")
    raw_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)
    digest = hashlib.sha256(html.encode()).hexdigest()[:12]
    (raw_dir / f"jsm-living_{today}_{digest}.html").write_text(html)

    rows = parse_units(html, today)
    out = data_dir / f"jsm-living_{today}.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    no_price = sum(r["rent_unit_min"] is None and r["rent_person_min"] is None for r in rows)
    no_beds = sum(r["beds"] is None for r in rows)
    print(f"{len(rows)} unit types -> {out}  (no price: {no_price}, no beds: {no_beds})")
    if not rows:
        print("No units parsed. Check the saved HTML in raw/.")


if __name__ == "__main__":
    main()