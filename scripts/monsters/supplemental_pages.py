"""
Author:  DayV
Email:   dayv6842@gmail.com
Website: https://www.osrsbox.com

Description:
Capture OSRS Wiki pages for attackable cache monsters that the Monsters category
listing does not cover. Some monsters (the Doom of Mokhaiotl larvae) are filed by
the Wiki as non-player characters and use {{Infobox NPC}}, so the category fetch
and the monster infobox parser never see them.

The manifest records the exact page revision, timestamp and categories so the
follow-up monster regeneration is reproducible from the captured page text.

Copyright (c) 2026, DayV

###############################################################################
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
###############################################################################
"""

import hashlib
import json
import logging
from pathlib import Path

import requests

import config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

WIKI_API_URL = "https://oldschool.runescape.wiki/api.php"
MANIFEST_PATH = Path(config.DATA_MONSTERS_PATH / "monsters-supplemental-pages.json")
WIKITEXT_PATH = Path(config.DATA_MONSTERS_PATH / "monsters-wiki-page-text.json")

# Cache monsters whose Wiki page is outside Category:Monsters and therefore is
# not captured by the normal category refresh. Each is named by its canonical
# Wiki page; versioned cache names redirect to that page.
SUPPLEMENTAL_PAGE_TITLES = ["Demonic larva"]


def _fetch_page(title: str) -> dict:
    page = title
    for _ in range(5):
        params = {
            "action": "query",
            "prop": "revisions|categories",
            "rvprop": "content|timestamp|ids",
            "rvslots": "main",
            "cllimit": "max",
            "redirects": "1",
            "format": "json",
            "titles": page,
        }
        response = requests.get(
            WIKI_API_URL, headers=config.custom_agent, params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()["query"]
        pages = list(data["pages"].values())
        if len(pages) != 1:
            raise RuntimeError(f"Wiki query for {title!r} returned {len(pages)} pages")
        result = pages[0]
        if "missing" in result:
            raise RuntimeError(f"Wiki page {title!r} does not exist")
        if "revisions" not in result:
            page = result["title"]
            continue
        revision = result["revisions"][0]
        if "categories" not in result:
            page = result["title"]
            continue
        categories = [category["title"] for category in result["categories"]]
        return {
            "title": result["title"],
            "revision": revision["revid"],
            "timestamp": revision["timestamp"],
            "source_url": "https://oldschool.runescape.wiki/w/"
            + result["title"].replace(" ", "_"),
            "categories": categories,
            "wikitext": revision["slots"]["main"]["*"],
        }
    raise RuntimeError(f"Wiki query for {title!r} did not return a complete revision")


def fetch():
    """Refresh the supplemental pages and their provenance manifest."""
    existing = {}
    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text())

    wikitext = {}
    if WIKITEXT_PATH.exists():
        wikitext = json.loads(WIKITEXT_PATH.read_text())

    pages = {}
    for requested_title in SUPPLEMENTAL_PAGE_TITLES:
        fetched = _fetch_page(requested_title)
        title = fetched.pop("title")
        text = fetched.pop("wikitext")
        digest = hashlib.sha256(text.encode()).hexdigest()
        wikitext[title] = text
        pages[title] = {
            "requested_title": requested_title,
            "revision": fetched["revision"],
            "timestamp": fetched["timestamp"],
            "source_url": fetched["source_url"],
            "categories": fetched["categories"],
            "sha256": digest,
        }
        logger.info("Captured %s revision %s (%s)", title, fetched["revision"], digest)

    existing["description"] = (
        "Attackable cache monsters whose OSRS Wiki page uses {{Infobox NPC}} and "
        "is outside Category:Monsters. Captured by scripts/monsters/supplemental_pages.py "
        "with the page revision and categories; the raw text lives in "
        "monsters-wiki-page-text.json."
    )
    existing["pages"] = pages
    MANIFEST_PATH.write_text(json.dumps(existing, indent=2) + "\n")
    WIKITEXT_PATH.write_text(json.dumps(wikitext, indent=4))


def load_pages() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text()).get("pages", {})


if __name__ == "__main__":
    fetch()
