"""Managers whose website shows AppFolio listings through a JSON feed
(Smile Student Living). Unlike the plain AppFolio page, the feed lets us read
whether a listing is priced per person.

Usage: python -m src.scrapers.appfolio_feed
"""

from __future__ import annotations

import json
import re

from src.scrapers.common import get, save

MANAGER = "Smile Student Living"
FEED = ("https://www.smilestudentliving.com/rts/collections/public/0af4bf1b/runtime/"
        "collection/appfolio-listings/query-data")
CITIES = re.compile(r",\s*(Champaign|Urbana|Savoy)\b", re.I)
PER_PERSON = re.compile(r"per[ -]person|individu\w* leas|by[ -]the[ -]bed|per bed", re.I)
MAX_PAGES = 20


def parse(listings: list[dict]) -> list[dict]:
    rows = []
    for x in listings:
        if not CITIES.search(x.get("full_address") or ""):
            continue
        beds = x.get("bedrooms")
        rent = x.get("market_rent") or None
        text = f"{x.get('marketing_title') or ''} {x.get('marketing_description') or ''}"
        per_person = bool(x.get("by_the_bed")) or bool(PER_PERSON.search(text))
        per_bed = rent if per_person or not rent else round(rent / max(beds or 1, 1))
        rows.append({
            "external_id": x["listable_uid"],
            "name": x["full_address"],
            "beds": beds, "baths": x.get("bathrooms"),
            "rent_per_bed_min": per_bed, "rent_per_bed_max": per_bed,
            "rent_unit": None if per_person else rent,
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
