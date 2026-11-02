"""
Description:
Program to generate the OSRS weapon equipment-stat JSON dump.

Reads the wiki's equipment-stat table (the ``infobox_bonuses`` bucket) and joins
each stat row to its item IDs through the ``infobox_item`` bucket, then writes
item ID -> stats for every row worn in the weapon or two-handed slot to
``docs/weapon-stats.json``: the page (version) the row came from, slot, combat
style, attack speed, attack range and the 14 equipment bonuses, named as in
``items-json``. A field the wiki leaves empty is omitted.

The join: an item row takes the stat row of the same page version
(``page_name_sub``), or its page's only stat row when the page has one. An item
ID listed by two pages keeps the first.

``--save-export`` keeps the raw bucket rows, and ``--from-export`` rebuilds the
dump from such a file without the network, so a dump can be reproduced exactly.

Usage:
    python -m scripts.weapons.update
    python -m scripts.weapons.update --save-export /tmp/weapon-bucket.json
    python -m scripts.weapons.update --from-export /tmp/weapon-bucket.json

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
from pathlib import Path
from typing import Dict, List, Optional

import requests

import config
from builders.run_log import begin_run
from scripts.examines.update import BUCKET_PAGE, wiki_json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

WEAPON_SLOTS = ("weapon", "2h")

# The wiki's bonus column -> the items-json equipment name, in the cache's stat order.
BONUS_COLUMNS = [
    ("stab_attack_bonus", "attack_stab"),
    ("slash_attack_bonus", "attack_slash"),
    ("crush_attack_bonus", "attack_crush"),
    ("magic_attack_bonus", "attack_magic"),
    ("range_attack_bonus", "attack_ranged"),
    ("stab_defence_bonus", "defence_stab"),
    ("slash_defence_bonus", "defence_slash"),
    ("crush_defence_bonus", "defence_crush"),
    ("magic_defence_bonus", "defence_magic"),
    ("range_defence_bonus", "defence_ranged"),
    ("strength_bonus", "melee_strength"),
    ("ranged_strength_bonus", "ranged_strength"),
    ("magic_damage_bonus", "magic_damage"),
    ("prayer_bonus", "prayer"),
]

# The wiki's other columns -> the dump's name.
STAT_COLUMNS = [
    ("equipment_slot", "slot"),
    ("combat_style", "combat_style"),
    ("weapon_attack_speed", "attack_speed"),
    ("weapon_attack_range", "attack_range"),
]

BONUS_FIELDS = ["page_name", "page_name_sub"] + [
    column for column, _ in STAT_COLUMNS + BONUS_COLUMNS
]
ITEM_FIELDS = ["page_name", "page_name_sub", "item_id"]


def bucket_rows(
    session: requests.Session, bucket: str, fields: List[str]
) -> List[dict]:
    """Every row of a wiki bucket, ``BUCKET_PAGE`` at a time."""
    select = ",".join(f"'{field}'" for field in fields)
    rows: List[dict] = []
    offset = 0
    while True:
        query = (
            f"bucket('{bucket}').select({select})"
            f".limit({BUCKET_PAGE}).offset({offset}).run()"
        )
        page = wiki_json(session, {"action": "bucket", "query": query}).get(
            "bucket", []
        )
        rows.extend(page)
        if len(page) < BUCKET_PAGE:
            return rows
        offset += BUCKET_PAGE


def fetch_export() -> dict:
    """The raw ``infobox_bonuses`` and ``infobox_item`` rows."""
    session = requests.Session()
    bonuses = bucket_rows(session, "infobox_bonuses", BONUS_FIELDS)
    items = bucket_rows(session, "infobox_item", ITEM_FIELDS)
    logger.info("Fetched %d stat rows and %d item rows", len(bonuses), len(items))
    return {"bonuses": bonuses, "items": items}


def version_of(row: dict) -> str:
    """The page version a row describes: its ``page_name_sub``, else its page."""
    sub = row.get("page_name_sub")
    return row["page_name"] if sub is None else sub


def stat_rows_by_item(export: dict) -> Dict[int, dict]:
    """Item ID -> its ``infobox_bonuses`` row, joined through ``infobox_item``."""
    by_version: Dict[str, dict] = {}
    by_page: Dict[str, List[dict]] = {}
    for row in export["bonuses"]:
        by_version[version_of(row)] = row
        by_page.setdefault(row["page_name"], []).append(row)

    rows: Dict[int, dict] = {}
    for item in export["items"]:
        row = by_version.get(version_of(item))
        if row is None:
            page_rows = by_page.get(item["page_name"], [])
            row = page_rows[0] if len(page_rows) == 1 else None
        if row is None:
            continue
        for value in item.get("item_id") or []:
            try:
                item_id = int(value)
            except (TypeError, ValueError):
                continue
            rows.setdefault(item_id, row)
    return rows


def number(value):
    """The bucket gives some numbers as text (attack range is "1"); those become ints."""
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return value


def weapon_stats(row: dict) -> dict:
    """The dump entry for one stat row; empty wiki fields are left out."""
    entry = {"page": version_of(row)}
    for column, name in STAT_COLUMNS:
        if row.get(column) is not None:
            entry[name] = (
                number(row[column]) if name.startswith("attack_") else row[column]
            )
    bonuses = {
        name: row[column]
        for column, name in BONUS_COLUMNS
        if row.get(column) is not None
    }
    entry["bonuses"] = bonuses
    return entry


def weapon_dump(export: dict) -> Dict[int, dict]:
    """Item ID -> stats, for the items whose stat row is a weapon slot's."""
    return {
        item_id: weapon_stats(row)
        for item_id, row in sorted(stat_rows_by_item(export).items())
        if str(row.get("equipment_slot", "")).lower() in WEAPON_SLOTS
    }


def write_dump(dump: Dict[int, dict], out_file: Path) -> None:
    """One item per line, so a wiki edit shows as a one-line diff."""
    lines = [
        f"{json.dumps(str(item_id))}:{json.dumps(entry, ensure_ascii=False, separators=(',', ':'))}"
        for item_id, entry in dump.items()
    ]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


def generate(
    out_file: Path,
    from_export: Optional[Path] = None,
    save_export: Optional[Path] = None,
) -> None:
    """Fetch (or read) the wiki rows and write the weapon dump."""
    if from_export is not None:
        export = json.loads(from_export.read_text(encoding="utf-8"))
    else:
        export = fetch_export()
    if save_export is not None:
        save_export.parent.mkdir(parents=True, exist_ok=True)
        save_export.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")

    dump = weapon_dump(export)
    write_dump(dump, out_file)
    logger.info("Wrote %d weapons to %s", len(dump), out_file)


def main():
    parser = argparse.ArgumentParser(
        description="Generate the OSRS weapon equipment-stat JSON dump."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=config.DOCS_WEAPON_STATS_FILE,
        help="File to write the dump to.",
    )
    parser.add_argument(
        "--from-export",
        type=Path,
        default=None,
        help="Build from saved bucket rows instead of fetching them.",
    )
    parser.add_argument(
        "--save-export",
        type=Path,
        default=None,
        help="Also write the raw bucket rows to this file.",
    )
    args = parser.parse_args()

    begin_run("scripts_weapons_update")
    generate(
        out_file=args.out, from_export=args.from_export, save_export=args.save_export
    )


if __name__ == "__main__":
    main()
