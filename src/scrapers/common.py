"""Shared plumbing for the newer scrapers.

Every scraper built on this writes the same "standard" columns, so one normalizer
(src.normalize.from_standard) handles all of them:

    manager, external_id, scraped_on, name, beds, baths,
    rent_per_bed_min, rent_per_bed_max, rent_unit, status, available, url

status is one of: Available, Last unit, Leased, Sold out, Unavailable.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from datetime import date
from pathlib import Path

import requests

USER_AGENT = os.getenv("USER_AGENT", "ChampaignLeaseIntel/0.1 (student research project)")
STANDARD_FIELDS = [
    "manager", "external_id", "scraped_on", "name", "beds", "baths",
    "rent_per_bed_min", "rent_per_bed_max", "rent_unit", "status", "available", "url",
]
MONEY_RE = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d+)?)")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def money(text) -> float | None:
    """'$1,105/Person' -> 1105.0; '8973' -> 8973.0; numbers pass through; else None."""
    if isinstance(text, (int, float)):
        return float(text) if text else None
    m = MONEY_RE.search(text or "")
    return float(m.group(1).replace(",", "")) if m else None


def get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def save(manager: str, rows: list[dict], raw_text: str, today: date | None = None) -> Path:
    """Write data/<slug>_<date>.csv and keep the raw page/JSON in raw/ (not published)."""
    today = today or date.today()
    slug = slugify(manager)
    Path("raw").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    digest = hashlib.sha256(raw_text.encode()).hexdigest()[:12]
    Path(f"raw/{slug}_{today}_{digest}.txt").write_text(raw_text)
    out = Path(f"data/{slug}_{today}.csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STANDARD_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"manager": manager, "scraped_on": today.isoformat(), **r})
    priced = sum(r.get("rent_per_bed_min") is not None for r in rows)
    print(f"{len(rows)} listings ({priced} with a price) -> {out}")
    if not rows:
        print("No listings parsed. Check the saved page in raw/.")
    return out
