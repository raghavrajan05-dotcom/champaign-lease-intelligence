"""Scrape rental listings from a property manager's AppFolio listings page.

Usage:
    python -m src.scrapers.appfolio --base-url https://campuspm.appfolio.com \
        --manager "Community Property Management"

Add --cities Champaign Urbana Savoy for managers that also list other towns.

Writes one CSV per run to data/ and saves the raw HTML to raw/ (both gitignored).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

USER_AGENT = os.getenv(
    "USER_AGENT", "ChampaignLeaseIntel/0.1 (student research project)"
)
DETAIL_RE = re.compile(r"/listings/detail/([0-9a-f-]{36})")
ADDRESS_RE = re.compile(r"[^\n]*?,\s*(?:Champaign|Urbana|Savoy),\s*IL\s*\d{5}")

FIELDS = [
    "manager", "external_id", "scraped_on", "title", "address",
    "rent", "price_basis", "beds", "baths", "sqft",
    "available_date", "available_raw", "url",
]


# ---------- small parsers (pure functions, easy to test) ----------

def parse_money(text: str | None) -> float | None:
    """'$1,250' -> 1250.0"""
    if not text:
        return None
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else None


def parse_int(text: str | None) -> int | None:
    """'1,000' -> 1000"""
    if not text:
        return None
    m = re.search(r"[\d,]+", text)
    return int(m.group(0).replace(",", "")) if m else None


def parse_bed_bath(text: str | None) -> tuple[int | None, float | None]:
    """'2 bd / 1.5 ba' -> (2, 1.5); 'Studio / 1 ba' -> (0, 1.0); '1 bd' -> (1, None)"""
    if not text:
        return None, None
    t = text.lower()
    beds = 0 if "studio" in t else None
    if (m := re.search(r"(\d+)\s*bd", t)):
        beds = int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*ba", t)
    baths = float(m.group(1)) if m else None
    return beds, baths


def parse_available(text: str | None, today: date) -> date | None:
    """'1/15/27' -> 2027-01-15; 'NOW' -> today"""
    if not text:
        return None
    t = text.strip().upper()
    if t == "NOW":
        return today
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


# ---------- page parsing ----------

def _listing_container(link: Tag, listing_id: str) -> Tag:
    """Climb from a detail link to the element holding just this one listing."""
    node = link
    best = link
    while node.parent is not None and node.parent.name != "[document]":
        parent = node.parent
        ids = {m.group(1) for a in parent.find_all("a", href=True)
               if (m := DETAIL_RE.search(a["href"]))}
        if ids != {listing_id}:
            break
        best = parent
        node = parent
    return best


def _label_values(container: Tag) -> dict[str, str]:
    """Collect label -> value pairs such as RENT -> $1,250."""
    out: dict[str, str] = {}
    for dt in container.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            out[dt.get_text(" ", strip=True).upper()] = dd.get_text(" ", strip=True)
    return out


def parse_listings(html: str, base_url: str, manager: str, today: date) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, Tag] = {}
    for a in soup.find_all("a", href=True):
        m = DETAIL_RE.search(a["href"])
        if m and m.group(1) not in seen:
            seen[m.group(1)] = a

    rows = []
    for listing_id, link in seen.items():
        box = _listing_container(link, listing_id)
        kv = _label_values(box)
        text = box.get_text("\n", strip=True)

        title_el = box.find(["h2", "h3"])
        addr_el = box.select_one(".js-listing-address, .listing-item__address")
        if addr_el:
            address = addr_el.get_text(" ", strip=True)
        else:
            m = ADDRESS_RE.search(text)
            address = m.group(0).strip() if m else None

        beds, baths = parse_bed_bath(kv.get("BED / BATH"))
        available_raw = kv.get("AVAILABLE")
        rows.append({
            "manager": manager,
            "external_id": listing_id,
            "scraped_on": today.isoformat(),
            "title": title_el.get_text(" ", strip=True) if title_el else None,
            "address": address,
            "rent": parse_money(kv.get("RENT")),
            "price_basis": "per_unit",  # AppFolio shows whole-unit rent
            "beds": beds,
            "baths": baths,
            "sqft": parse_int(kv.get("SQUARE FEET")),
            "available_date": (d.isoformat() if (d := parse_available(available_raw, today)) else None),
            "available_raw": available_raw,
            "url": f"{base_url.rstrip('/')}/listings/detail/{listing_id}",
        })
    return rows


def keep_cities(rows: list[dict], cities: list[str] | None) -> list[dict]:
    """Keep listings whose address names one of the cities (all rows if no cities given)."""
    if not cities:
        return rows
    pattern = re.compile(r",\s*(" + "|".join(map(re.escape, cities)) + r")\b", re.I)
    return [r for r in rows if r["address"] and pattern.search(r["address"])]


# ---------- run ----------

def fetch(base_url: str) -> str:
    resp = requests.get(
        f"{base_url.rstrip('/')}/listings/listings",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--manager", required=True)
    ap.add_argument("--cities", nargs="*", help="only keep listings in these cities")
    args = ap.parse_args()

    today = date.today()
    slug = re.sub(r"[^a-z0-9]+", "-", args.manager.lower()).strip("-")
    html = fetch(args.base_url)

    raw_dir, data_dir = Path("raw"), Path("data")
    raw_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)
    digest = hashlib.sha256(html.encode()).hexdigest()[:12]
    (raw_dir / f"{slug}_{today}_{digest}.html").write_text(html)

    rows = keep_cities(parse_listings(html, args.base_url, args.manager, today), args.cities)
    out = data_dir / f"{slug}_{today}.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    missing_rent = sum(r["rent"] is None for r in rows)
    print(f"{len(rows)} listings -> {out}  (missing rent: {missing_rent})")
    if not rows:
        print("No listings parsed. Check the saved HTML in raw/.")


if __name__ == "__main__":
    main()
