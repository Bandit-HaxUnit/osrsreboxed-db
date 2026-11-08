"""
Author:  PH01L
Email:   phoil@osrsbox.com
Website: https://www.osrsbox.com

Description:
Tests for module: docs/items-json

Copyright (c) 2020, PH01L

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
import validator


def test_item_database():
    """Unit test to check item database contents against JSON schema."""
    # Read in the item schema file
    path_to_schema = Path(config.DATA_SCHEMAS_PATH / "schema-items.json")
    with open(path_to_schema, "r") as f:
        schema = json.loads(f.read())

    # Validator object with schema attached
    v = validator.MyValidator(schema)

    # Set the path to the items-json folder and get all the JSON files
    path_to_items_json_dir = Path(config.DOCS_PATH / "items-json")
    fis = path_to_items_json_dir.glob("*.json")
    fis = sorted(fis)

    # Validate each file
    for json_file in fis:
        with open(json_file) as fi:
            item = json.load(fi)
            assert v.validate(item), (
                f"Validation failed for {json_file} (id={item.get('id')}). "
                f"Errors: {v.errors}"
            )


def test_item_alch_export():
    """Ensure the purpose-specific alchemy export matches the item database."""
    with open(config.DOCS_PATH / "items-complete.json", encoding="utf-8") as f:
        items = json.load(f)
    with open(config.DOCS_PATH / "item-alch.json", encoding="utf-8") as f:
        item_alch = json.load(f)
    from builders.items.unalchable import WikiUnalchable

    with open(config.DATA_ITEMS_PATH / "items-unalchable.json", encoding="utf-8") as f:
        unalchable = json.load(f)
    with open(config.DATA_ITEMS_PATH / "items-wiki-page-text.json", encoding="utf-8") as f:
        is_unalchable = WikiUnalchable(unalchable, json.load(f))

    expected = {
        item_id: {
            "id": item["id"],
            "highalch": item["highalch"],
            "lowalch": item["lowalch"],
        }
        for item_id, item in items.items()
        if (isinstance(item["highalch"], int) and isinstance(item["lowalch"], int))
        or (item["highalch"] is None and item["lowalch"] is None and is_unalchable(item["wiki_name"], item["wiki_url"]))
    }

    assert item_alch == expected


def test_item_alch_versioned_unalchables():
    """Versioned untradeables the wiki marks unalchable are left out of the alchemy export.

    Their wiki_name ("Dragon defender (Normal)") is not a page title in the unalchable
    category, so the page name and the infobox's per-version "alchable" decide.
    """
    with open(config.DOCS_PATH / "item-alch.json", encoding="utf-8") as f:
        item_alch = json.load(f)
    def unalchable(item_id):
        return item_alch[item_id]["highalch"] is None and item_alch[item_id]["lowalch"] is None

    # Dragon defender, Fire cape, Rune pouch, Fighter torso: "alchable = No" on every version,
    # written with null values so a consumer clears its own.
    for item_id in ("12954", "6570", "12791", "10551"):
        assert unalchable(item_id), item_id
    # Mining helmet: Unlit (5014) is alchable, Lit (5013) is not. Iban's staff (broken) alchs.
    assert not unalchable("5014")
    assert unalchable("5013")
    assert item_alch["1410"]["highalch"] == 12
    # No alch values in the item files, but nothing says they can't be alchemised: left out of the export,
    # not written as null (bird nests with red/green/blue eggs, the soft clay and essence packs).
    for item_id in ("5070", "5071", "5072", "25533", "25535"):
        assert item_id not in item_alch, item_id


def test_unalchable_rule():
    """The infobox answer wins; the category is matched by wiki name, page name or version."""
    from builders.items.unalchable import is_unalchable, page_name_from_url, version_from_url

    category = {"Dragon defender", "Mining helmet"}
    url = "https://oldschool.runescape.wiki/w/Dragon_defender#Normal"
    assert page_name_from_url(url) == "Dragon defender"
    assert version_from_url(url) == "Normal"
    assert is_unalchable(category, "Dragon defender (Normal)", "Dragon defender")
    assert not is_unalchable(category, "Mining helmet (Unlit)", "Mining helmet", alchable=True)
    assert is_unalchable(set(), "Anything", alchable=False)
    assert not is_unalchable(category, "Abyssal whip", "Abyssal whip")


def test_items_cache_data_noteable_key():
    """Ensure item cache data includes noteable for every item."""
    path_to_cache = Path(config.DATA_ITEMS_PATH / "items-cache-data.json")
    with open(path_to_cache, "r") as f:
        cache_data = json.load(f)

    for item_id, item_data in cache_data.items():
        assert "noteable" in item_data, f"Missing noteable for cache item {item_id}"
        assert isinstance(
            item_data["noteable"], bool
        ), f"Cache item {item_id} noteable must be a boolean"
