"""
Author:  PH01L
Email:   phoil@osrsbox.com
Website: https://www.osrsbox.com

Description:
Script to fetch and process OSRS Wiki pages for Category:Monsters.

Copyright (c) 2021, PH01L

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

import json
from pathlib import Path

import config
from scripts.wiki.wiki_properties import WikiProperties
from scripts.wiki.wikitext_parser import WikitextTemplateParser
from scripts.monsters import supplemental_pages


def fetch():
    """Get all the wiki category page titles and page text for monsters."""
    wiki_props = WikiProperties(
        categories=["Monsters"],
        template_names=["infobox monster"],
        titles_filepath=Path(
            config.DATA_MONSTERS_PATH / "monsters-wiki-page-titles.json"
        ),
        text_filepath=Path(config.DATA_MONSTERS_PATH / "monsters-wiki-page-text.json"),
        processed_filepath=Path(
            config.DATA_MONSTERS_PATH / "monsters-wiki-page-text-processed.json"
        ),
    )
    wiki_props.fetch()


def process():
    """Process wiki page text and extract monster infobox data."""
    wiki_props = WikiProperties(
        categories=["Monsters"],
        template_names=["infobox monster"],
        titles_filepath=Path(
            config.DATA_MONSTERS_PATH / "monsters-wiki-page-titles.json"
        ),
        text_filepath=Path(config.DATA_MONSTERS_PATH / "monsters-wiki-page-text.json"),
        processed_filepath=Path(
            config.DATA_MONSTERS_PATH / "monsters-wiki-page-text-processed.json"
        ),
    )
    wiki_props.process()
    _add_supplemental_pages()


def _add_supplemental_pages():
    """Map captured {{Infobox NPC}} monster pages into the processed dump."""
    pages = supplemental_pages.load_pages()
    if not pages:
        return

    processed_filepath = Path(
        config.DATA_MONSTERS_PATH / "monsters-wiki-page-text-processed.json"
    )
    with open(processed_filepath) as f:
        export = json.load(f)
    with open(
        Path(config.DATA_MONSTERS_PATH / "monsters-wiki-page-text.json")
    ) as f:
        wikitext_dump = json.load(f)

    for page_name in pages:
        wikitext = wikitext_dump.get(page_name)
        if not wikitext:
            raise RuntimeError(f"Supplemental page {page_name!r} has no captured text")
        parser = WikitextTemplateParser(wikitext)
        if not parser.extract_infobox("infobox npc"):
            raise RuntimeError(f"Supplemental page {page_name!r} has no Infobox NPC")
        parser.determine_infobox_versions()
        for monster_id, version_number in parser.extract_infobox_ids(
            include_historical=True
        ).items():
            export[str(monster_id)] = [page_name, version_number, 1, wikitext]

    with open(processed_filepath, "w") as f:
        json.dump(export, f, indent=4)


if __name__ == "__main__":
    fetch()
    process()
