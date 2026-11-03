"""Scrape Green Street Realty's student property list.

Usage:
    python -m src.scrapers.greenstreet

The search page lists properties (buildings), not individual units, with
price ranges such as "$800 - $1,150 /bed". This writes one row per property
to data/ and saves the raw HTML to raw/ (both gitignored).
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.greenstrealty.com"
SEARCH_URL = f"{BASE_URL}/properties/search/student"
MANAGER = "Green Street Realty"
USER_AGENT = os.getenv(
    "USER_AGENT", "ChampaignLeaseIntel/0.1 (student research project)"
)
MIN_REAL_RENT = 100  # values like "$0 /bed" or "$10 /mth" are placeholders

PROFILE_RE = re.compile(r"/properties/profile/([a-z0-9-]+)", re.I)
MONEY = r"\$\s*([\d,]+)"
PER_BED_RE = re.compile(MONEY + r"(?:\s*-\s*" + MONEY + r")?\s*/\s*bed", re.I)
PER_MONTH_RE = re.compile(MONEY + r"(?:\s*-\s*" + MONEY + r")?\s*/\s*(?:mth|mo|month)", re.I)
BEDS_RE = re.compile(r"(\d+)\s*(?:-\s*(\d+)|(\+))?\s*(?:bed(?:room)?s?|br)\b", re.I)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?)|(\+))?\s*(?:bath(?:room)?s?|ba)\b", re.I)
AVAIL_RE = re.compile(r"Available\s+(Now|[A-Z][a-z]+\s+\d{4})", re.I)

FIELDS = [
    "manager", "external_id", "scraped_on", "name",
    "rent_per_bed_min", "rent_per_bed_max", "rent_per_unit_min", "rent_per_unit_max",
    "beds_min", "beds_max", "baths_min", "baths_max", "available_raw", "url",
]


def _money(s: str | None) -> float | None:
    if not s:
        return None
    v = float(s.replace(",", ""))
    return v if v >= MIN_REAL_RENT else None


def parse_range(regex: re.Pattern, text: str, cast=float):
    """Return (low, high) from text like '$800 - $1,150 /bed' or '1-4 Bed'.

    A single value gives (v, v); '5+' gives (5, None) because the top is unknown.
    """
    m = regex.search(text)
    if not m:
        return None, None
    groups = m.groups()
    lo_raw, hi_raw = groups[0], groups[1]
    plus = groups[2] if len(groups) > 2 else None
    if cast is _money:
        lo, hi = _money(lo_raw), _money(hi_raw) if hi_raw else _money(lo_raw)
        return lo, hi
    lo = cast(lo_raw)
    if plus:
        return lo, None
    return lo, cast(hi_raw) if hi_raw else lo


def _card(link: Tag, slug: str) -> Tag:
    """Climb from a profile link to the element holding just this one property."""
    node = best = link
    while node.parent is not None and node.parent.name != "[document]":
        parent = node.parent
        slugs = {m.group(1).lower() for a in parent.find_all("a", href=True)
                 if (m := PROFILE_RE.search(a["href"]))}
        if slugs != {slug}:
            break
        best = node = parent
    return best


def parse_properties(html: str, today: date) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, Tag] = {}
    for a in soup.find_all("a", href=True):
        m = PROFILE_RE.search(a["href"])
        if m and m.group(1).lower() not in seen:
            seen[m.group(1).lower()] = a

    rows = []
    for slug, link in seen.items():
        card = _card(link, slug)
        text = card.get_text(" ", strip=True)
        # Remove prices first so "$1,150 /bed" can't be misread as a bed count.
        no_prices = PER_MONTH_RE.sub(" ", PER_BED_RE.sub(" ", text))

        heading = card.find(["h2", "h3", "h4"])
        name = heading.get_text(" ", strip=True) if heading else slug.replace("-", " ").title()

        bed_lo, bed_hi = parse_range(PER_BED_RE, text, _money)
        unit_lo, unit_hi = parse_range(PER_MONTH_RE, text, _money)
        beds_lo, beds_hi = parse_range(BEDS_RE, no_prices, int)
        baths_lo, baths_hi = parse_range(BATHS_RE, no_prices, float)
        avail = AVAIL_RE.search(text)

        rows.append({
            "manager": MANAGER,
            "external_id": slug,
            "scraped_on": today.isoformat(),
            "name": name,
            "rent_per_bed_min": bed_lo, "rent_per_bed_max": bed_hi,
            "rent_per_unit_min": unit_lo, "rent_per_unit_max": unit_hi,
            "beds_min": beds_lo, "beds_max": beds_hi,
            "baths_min": baths_lo, "baths_max": baths_hi,
            "available_raw": avail.group(1) if avail else None,
            "url": f"{BASE_URL}/properties/profile/{slug}",
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
    (raw_dir / f"green-street-realty_{today}_{digest}.html").write_text(html)

    rows = parse_properties(html, today)
    out = data_dir / f"green-street-realty_{today}.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    no_price = sum(r["rent_per_bed_min"] is None and r["rent_per_unit_min"] is None for r in rows)
    print(f"{len(rows)} properties -> {out}  (no price: {no_price})")
    if not rows:
        print("No properties parsed. Check the saved HTML in raw/.")


if __name__ == "__main__":
    main()
    