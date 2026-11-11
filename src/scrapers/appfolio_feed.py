"""Managers whose website shows AppFolio listings through a JSON feed
(Smile Student Living).

Smile's listed rent is PER PERSON. Evidence (Nov 2026 audit): 89 of 97 multi-bedroom
listings say "priced per person" / "individual leasing"; in every listing whose
description also states the whole-unit price, that price equals rent x bedrooms
(e.g. 303 E Green 3x3: $719 listed, "$2,157" for the unit); and the office confirmed it
by phone. The utility fee in each description is per UNIT, so we split it by bedrooms.

Usage: python -m src.scrapers.appfolio_feed
"""

from __future__ import annotations

import json
import re

from src.normalize import BASIS_ONE_BED, BASIS_PER_PERSON
from src.scrapers.common import get, money, save

MANAGER = "Smile Student Living"
FEED = ("https://www.smilestudentliving.com/rts/collections/public/0af4bf1b/runtime/"
        "collection/appfolio-listings/query-data")
CITIES = re.compile(r",\s*(Champaign|Urbana|Savoy)\b", re.I)
UTILITY_FEE = re.compile(r"utility fee of\s*\$\s*([\d,]+(?:\.\d+)?)", re.I)
MAX_PAGES = 20


def parse(listings: list[dict]) -> list[dict]:
    rows = []
    for x in listings:
        if not CITIES.search(x.get("full_address") or ""):
            continue
        beds = x.get("bedrooms")
        per_bed = x.get("market_rent") or None  # per person (see module docstring)
        fee = UTILITY_FEE.search(re.sub(r"<[^>]+>", " ", x.get("marketing_description") or ""))
        fee_per_bed = round(money(fee.group(1)) / max(beds or 1, 1)) if fee else None
        rows.append({
            "external_id": x["listable_uid"],
            "name": x["full_address"],
            "beds": beds, "baths": x.get("bathrooms"),
            "rent_per_bed_min": per_bed, "rent_per_bed_max": per_bed,
            "rent_unit": per_bed * max(beds or 1, 1) if per_bed else None,
            "price_basis": (BASIS_ONE_BED if (beds or 0) <= 1 else BASIS_PER_PERSON)
            if per_bed else None,
            "fees_per_bed": fee_per_bed,
            "status": "Available" if x.get("available") else "Unavailable",
            "available": x.get("available_date"),
            "url": f"{x['database_url'].rstrip('/')}/listings/detail/{x['listable_uid']}",
        })
    return rows


def main() -> None:
    listings, pages = [], []
    for n in range(MAX_PAGES):
        text = get(FEED, params={"pageSize": 100, "pageNumber": n, "query": "()",
                                 "language": "ENGLISH"}).text
        data = json.loads(text)
        pages.append(text)
        listings += [v["data"] for v in data.get("values", [])]
        if n + 1 >= data.get("page", {}).get("totalPages", 0):
            break
    save(MANAGER, parse(listings), "\n".join(pages))


if __name__ == "__main__":
    main()
