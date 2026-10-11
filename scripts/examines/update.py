"""
Description:
Program to generate the OSRS object (scenery) examine JSON dump.

Lists every scenery page from the wiki's ``infobox_scenery`` bucket, reads their
``{{Infobox Scenery}}`` 50 pages per request, and writes object ID -> examine text
to ``docs/object-examines.json`` (minified). An ID given different texts by two
pages keeps the first, and is logged.

Usage:
    python -m scripts.examines.update
    python -m scripts.examines.update --limit 200 --out /tmp/object-examines.json

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

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

import config
from builders.run_log import begin_run
from scripts.examines.examines_wikitext import examines_of, infoboxes

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

WIKI_API_URL = "https://oldschool.runescape.wiki/api.php"
BUCKET_PAGE = 5000
TITLES_PER_REQUEST = 50
MAX_ATTEMPTS = 5


def wiki_json(session: requests.Session, params: Dict[str, str]) -> dict:
    """A wiki API query, retried with backoff on network errors and non-JSON replies."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(
                WIKI_API_URL,
                headers=config.custom_agent,
                params={"format": "json", **params},
                timeout=30,
            )
            return response.json()
        except (requests.exceptions.RequestException, ValueError) as error:
            if attempt == MAX_ATTEMPTS:
                raise SystemExit(f">>> ERROR: wiki query failed: {error}") from error
            wait = 2**attempt
            logger.warning("Wiki query failed (%s), retrying in %ds", error, wait)
            time.sleep(wait)
    return {}


def scenery_pages(session: requests.Session) -> List[str]:
    """Every page with an Infobox Scenery, from the ``infobox_scenery`` bucket."""
    pages = set()
    offset = 0
    while True:
        query = (
            "bucket('infobox_scenery').select('page_name')"
            f".limit({BUCKET_PAGE}).offset({offset}).run()"
        )
        rows = wiki_json(session, {"action": "bucket", "query": query}).get("bucket", [])
        pages.update(row["page_name"] for row in rows if row.get("page_name"))
        if len(rows) < BUCKET_PAGE:
            return sorted(pages)
        offset += BUCKET_PAGE


def page_texts(session: requests.Session, titles: List[str]) -> Dict[str, str]:
    """The wikitext of up to 50 pages, by title."""
    result = wiki_json(
        session,
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": "|".join(titles),
            "redirects": "1",
        },
    )
    texts = {}
    for page in result.get("query", {}).get("pages", {}).values():
        revisions = page.get("revisions") or [{}]
        texts[page.get("title", "")] = revisions[0].get("slots", {}).get("main", {}).get("*", "")
    return texts


def generate(out_file: Path, limit: Optional[int] = None) -> None:
    """Read every scenery page and write the examine dump."""
    session = requests.Session()
    pages = scenery_pages(session)
    if limit is not None:
        pages = pages[:limit]
    logger.info("Processing %d scenery wiki pages...", len(pages))

    examines: Dict[int, str] = {}
    conflicts = 0
    for start in range(0, len(pages), TITLES_PER_REQUEST):
        batch = pages[start : start + TITLES_PER_REQUEST]
        for title, wikitext in page_texts(session, batch).items():
            for box in infoboxes(wikitext):
                for object_id, text in examines_of(box):
                    existing = examines.get(object_id)
                    if existing is None:
                        examines[object_id] = text
                    elif existing != text:
                        conflicts += 1
                        logger.info(
                            "Object %d: kept %r over %r (%s)", object_id, existing, text, title
                        )
        done = min(start + TITLES_PER_REQUEST, len(pages))
        if done % 1000 < TITLES_PER_REQUEST or done == len(pages):
            logger.info("Progress: %4d of %4d pages", done, len(pages))

    out_file.parent.mkdir(parents=True, exist_ok=True)
    dump = {str(object_id): examines[object_id] for object_id in sorted(examines)}
    out_file.write_text(
        json.dumps(dump, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    logger.info(
        "Wrote %d object examines to %s (%d IDs given differing texts)",
        len(dump),
        out_file,
        conflicts,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate the OSRS object examine JSON dump."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=config.DOCS_OBJECT_EXAMINES_FILE,
        help="File to write the dump to.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Only process this many wiki pages."
    )
    args = parser.parse_args()

    begin_run("scripts_examines_update")
    generate(out_file=args.out, limit=args.limit)


if __name__ == "__main__":
    main()
