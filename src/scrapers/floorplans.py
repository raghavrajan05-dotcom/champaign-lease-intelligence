"""Big student buildings that list floor plans (one row per plan, price per person).

Usage: python -m src.scrapers.floorplans octave|seven07|the-rive

Each building's site is built differently, so each has its own small parser:
  octave    WordPress page, plans in the HTML
  seven07   the EasyTour JSON feed its floor-plans page loads
  the-rive  floor-plan data embedded in the page's JavaScript
"""

from __future__ import annotations

import argparse
import json
import re

from bs4 import BeautifulSoup

from src.scrapers.common import get, money, save

BUILDINGS = {
    "octave": {"manager": "Octave", "address": "210 S 4th St",
               "url": "https://liveatoctave.com/floor-plans/"},
    "seven07": {"manager": "Seven07", "address": "707 S 4th St",
                "url": "https://cgsynergyapi-prod.wonderfulisland-00679a9d.centralus."
                       "azurecontainerapps.io/api/community/liveseven07.com",
                "page": "https://liveseven07.com/floor-plans/"},
    "the-rive": {"manager": "The Rive", "address": "212 E Green St",
                 "url": "https://www.therivechampaign.com/floor-plans/"},
}


def row(b: dict, plan: str, beds, baths, price, status: str, url: str) -> dict:
    return {"external_id": plan, "name": f"{b['address']} - {b['manager']} ({plan})",
            "beds": beds, "baths": baths, "rent_per_bed_min": price, "rent_per_bed_max": price,
            "rent_unit": None, "status": status, "available": None, "url": url}


def parse_octave(html: str, b: dict) -> list[dict]:
    rows = []
    for card in BeautifulSoup(html, "html.parser").select(".jet-portfolio__content-inner"):
        plan = card.select_one(".jet-portfolio__title").get_text(strip=True)
        desc = card.select_one(".jet-portfolio__desc").get_text(" ", strip=True)
        beds = re.search(r"(\d+)\s*Bed", desc)
        baths = re.search(r"(\d+(?:\.\d+)?)\s*Bath", desc)
        remaining = card.select_one(".floor-remaining")
        note = remaining.get_text(" ", strip=True).lower() if remaining else ""
        price = money(card.find("b").get_text() if card.find("b") else None)
        status = ("Sold out" if "sold" in note or "waitlist" in note
                  else "Last unit" if re.search(r"\b1 left|last", note) else "Available")
        rows.append(row(b, plan, int(beds.group(1)) if beds else None,
                        float(baths.group(1)) if baths else None,
                        price if status != "Sold out" else None, status, b["url"]))
    return rows


def parse_seven07(text: str, b: dict) -> list[dict]:
    rows = []
    for fp in json.loads(text).get("floorPlans", []):
        left = fp.get("unitsAvailable")
        status = ("Sold out" if left == 0 else "Last unit" if left == 1 else "Available")
        rows.append(row(b, fp["name"], int(fp["bedroomCount"]), fp.get("bathroomCount"),
                        money(fp.get("marketRent")), status, b["page"]))
    return rows


def parse_the_rive(html: str, b: dict) -> list[dict]:
    script = next(s.string for s in BeautifulSoup(html, "html.parser").find_all("script")
                  if s.string and "apiTransitionData" in s.string)
    start = script.index("{", script.index("localData.apiTransitionData"))
    data, _ = json.JSONDecoder().raw_decode(script[start:])
    rows = []
    for category in data["categories"].values():
        for fp in category["floorplans"]:
            rates = [r for r in (fp.get("rates") or []) if isinstance(r, dict)]
            prices = [money(r.get("special_value")) or money(r.get("value")) for r in rates]
            prices = [p for p in prices if p]
            status = "Sold out" if fp.get("sold_out") else "Available"
            rows.append(row(b, fp["name"], int(fp["beds"]), money(fp.get("baths")),
                            min(prices) if prices and status != "Sold out" else None,
                            status, b["url"]))
    return rows


PARSERS = {"octave": parse_octave, "seven07": parse_seven07, "the-rive": parse_the_rive}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("building", choices=BUILDINGS)
    key = ap.parse_args().building
    b = BUILDINGS[key]
    text = get(b["url"]).text
    save(b["manager"], PARSERS[key](text, b), text)


if __name__ == "__main__":
    main()
