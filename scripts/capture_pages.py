"""One-time research helper: save what each manager's listings page loads, so we can
write a scraper for it. NOT part of the daily pipeline.

Opens each page once in a real (headless) browser, waits for it to finish loading, and saves:
  raw/samples/<slug>/page.html        the page after JavaScript has run
  raw/samples/<slug>/responses.json   every data request the page made (URL + JSON body)
  raw/samples/<slug>/robots.txt       the site's robots.txt

Setup (once):  pip install playwright && python -m playwright install chromium
Run:           python scripts/capture_pages.py
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

USER_AGENT = "ChampaignLeaseIntel/0.1 (student research project)"
PAGES = {
    "roland-realty": "https://www.roland-realty.com/for-rent/available-fall/all-unit-listings?available=true",
    "roland-realty-p2": "https://www.roland-realty.com/for-rent/available-fall/all-unit-listings?available=true&page=2",
    "smile-student-living": "https://www.smilestudentliving.com/availability",
    "mhm-properties": "https://www.mhmproperties.com/apartments/",
    "bailey-apartments": "https://baileyapartments.com/amenities/",
    "bailey-apartments-list": "https://baileyapartments.com/apartment/",
    "the-dean": "https://www.thedean.com/campustown/price-calculator/",
    "seven07": "https://liveseven07.com/floor-plans/",
    "octave": "https://liveatoctave.com/floor-plans/",
    "the-rive": "https://www.therivechampaign.com/floor-plans/",
    "here-champaign": "https://herechampaign.com/availability",
    "309-green": "https://www.americancampus.com/student-apartments/il/champaign/309-green/floor-plans",
    "tower-at-3rd": "https://www.americancampus.com/student-apartments/il/champaign/tower-at-3rd/floor-plans",
    "yugo-urbana": "https://yugo.com/en-us/global/united-states-of-america/urbana-il/yugo-urbana-illinois/rooms",
}
OUT = Path("raw/samples")
MAX_BODY = 400_000  # characters kept per response


def save_robots(url: str, folder: Path) -> None:
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    try:
        r = requests.get(f"{root}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=20)
        (folder / "robots.txt").write_text(f"# {root}/robots.txt -> HTTP {r.status_code}\n{r.text}")
    except requests.RequestException as e:
        (folder / "robots.txt").write_text(f"# error: {e}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for slug, url in PAGES.items():
            folder = OUT / slug
            folder.mkdir(parents=True, exist_ok=True)
            page = browser.new_page(user_agent=USER_AGENT)
            captured = []

            def keep(resp):
                ctype = resp.headers.get("content-type", "")
                if resp.request.resource_type in ("xhr", "fetch") or "json" in ctype:
                    try:
                        body = resp.text()[:MAX_BODY]
                    except Exception:  # noqa: BLE001 (binary or closed response)
                        body = ""
                    captured.append({"url": resp.url, "status": resp.status,
                                     "type": ctype, "body": body})

            page.on("response", keep)
            try:
                page.goto(url, wait_until="networkidle", timeout=60_000)
            except Exception as e:  # noqa: BLE001 (keep whatever loaded)
                print(f"  {slug}: page didn't fully settle ({type(e).__name__}), saving anyway")
            page.wait_for_timeout(4000)
            (folder / "page.html").write_text(page.content())
            (folder / "responses.json").write_text(json.dumps(captured, indent=1))
            page.close()
            save_robots(url, folder)
            n_json = sum("json" in c["type"] for c in captured)
            print(f"{slug:24s} html {len((folder / 'page.html').read_text()):>8,} chars, "
                  f"{len(captured)} data requests ({n_json} JSON)")
            time.sleep(2)  # be polite between sites
        browser.close()


if __name__ == "__main__":
    main()
