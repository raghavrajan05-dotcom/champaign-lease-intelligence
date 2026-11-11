"""MHM Properties: one card per building, one price line per apartment type.

Usage: python -m src.scrapers.mhm
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.normalize import BASIS_ONE_BED, BASIS_PER_PERSON, BASIS_SPLIT
from src.scrapers.common import get, money, save

MANAGER = "MHM Properties"
URL = "https://www.mhmproperties.com/apartments/"
BEDS_RE = re.compile(r"(\d+)\s*(?:Bed|Bedroom)", re.I)
BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Bath|ba)", re.I)


def parse_line(line: str, per_person_card: bool = False) -> dict:
    """'2 Bed/2 Bath: From $1,105/Person' -> beds 2, baths 2, price 1105, Available."""
    label, _, value = line.partition(":")
    value = value.strip(" :") or label
    upper = value.upper()
    if "LEASED" in upper:
        status = "Leased"
    elif "LAST UNIT" in upper:
        status = "Last unit"
    else:
        status = "Available"
    prices = [float(p.replace(",", "")) for p in re.findall(r"\$\s*([\d,]+)", value)]
    beds = BEDS_RE.search(label)
    baths = BATHS_RE.search(label)
    lo = min(prices) if prices and status != "Leased" else None
    hi = max(prices) if prices and status != "Leased" else None
    per_person = per_person_card or "PERSON" in upper
    n_beds = int(beds.group(1)) if beds else None
    basis = BASIS_ONE_BED if (n_beds or 0) <= 1 else BASIS_PER_PERSON if per_person else BASIS_SPLIT
    if lo is not None and basis == BASIS_SPLIT:  # whole-unit price: split by beds
        lo, hi = round(lo / n_beds), round(hi / n_beds)
    return {"plan": label.strip(), "beds": n_beds,
            "price_basis": basis if lo is not None else None,
            "baths": float(baths.group(1)) if baths else None,
            "rent_per_bed_min": lo, "rent_per_bed_max": hi, "status": status}


def parse(html: str) -> list[dict]:
    rows = []
    for card in BeautifulSoup(html, "html.parser").select("div.propgridc"):
        building = card.h2.get_text(strip=True) if card.h2 else None
        link = card.find("a", href=True)
        per_person = "price per person" in card.get_text(" ", strip=True).lower()
        for p in card.select("p.ppricebox"):
            line = parse_line(p.get_text(" ", strip=True), per_person)
            plan = line.pop("plan")
            rows.append({"external_id": f"{building} | {plan}",
                         "name": f"{building} ({plan})",  # geocoder ignores the "(...)"
                         "rent_unit": None, "available": None,
                         "url": link["href"] if link else URL, **line})
    return rows


def main() -> None:
    html = get(URL).text
    save(MANAGER, parse(html), html)


if __name__ == "__main__":
    main()
