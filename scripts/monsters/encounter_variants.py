"""Export named encounter variants without assigning or replacing normal NPC IDs.

The manifest holds source anchors only. Statistics use the canonical monster
builder and drops use the canonical drop parser. This is needed for encounter
variants whose Wiki ID is ``overrideNNN`` or whose NPC ID is shared with a normal
boss. Uncertain max-hit text remains unresolved instead of becoming an estimate.
"""

import argparse
import json
import re
from pathlib import Path

import mwparserfromhell

import config
from builders.monsters.build_monster import BuildMonster
from builders.monsters import infobox_cleaner
from osrsreboxed import items_api
from scripts.drops import drops_tables, drops_wikitext

MANIFEST = config.DATA_MONSTERS_PATH / "encounter-variants.json"
PAGES = config.DATA_MONSTERS_PATH / "monsters-wiki-page-text.json"


def profile_from_page(page, text, version=None):
    """Parse a named page/version with exactly the ordinary monster cleaners."""
    templates = [
        template for template in mwparserfromhell.parse(text).filter_templates()
        if str(template.name).strip().lower() == "infobox monster"
    ]
    if len(templates) != 1:
        raise ValueError("Expected one Infobox Monster: " + page)
    builder = BuildMonster.__new__(BuildMonster)
    builder.monster_dict = {}
    builder.monster_name = page
    builder.wikitext_found_using = "name"
    builder.infobox_version_number = version
    builder.template = templates[0]
    builder.populate_monster_properties_from_wiki_data()
    row = builder.monster_dict
    suffix = "" if version is None else str(version)

    def value(name):
        return (builder.extract_infobox_value(builder.template, name + suffix)
                or builder.extract_infobox_value(builder.template, name))

    def present(name):
        """A field's text, or None when the Wiki leaves it blank or out (never a stand-in 0 or "")."""
        raw = value(name)
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    row["name"] = infobox_cleaner.clean_wikitext(value("name") or page)
    size = present("size")
    row["size"] = infobox_cleaner.stats(size) if size is not None else None
    row["freeze_resistance"] = builder.freeze_resistance
    row["max_hits"] = builder.max_hits
    row["source_page"] = page
    row["source_version"] = version
    row["source_id"] = present("id")
    if not isinstance(row.get("hitpoints"), int) or row["hitpoints"] <= 0:
        raise ValueError("Missing positive hitpoints: " + page)
    if not isinstance(row.get("attack_speed"), int) or row["attack_speed"] <= 0:
        raise ValueError("Missing attack speed: " + page)
    return row


def drops_section(text):
    """Select the current Drops section; exclude historical drops and strategies."""
    match = re.search(r"^==\s*Drops\s*==\s*$", text, re.M | re.I)
    if not match:
        raise ValueError("Page has no Drops section")
    remainder = text[match.end():]
    end = re.search(r"^==[^=].*?==\s*$", remainder, re.M)
    return remainder[:end.start()] if end else remainder


def normal_sources(text):
    """Follow Wiki Main anchors rather than duplicating ordinary loot tables."""
    sources = []
    for template in mwparserfromhell.parse(drops_section(text)).filter_templates():
        if str(template.name).strip().lower() != "main":
            continue
        for parameter in template.params:
            if str(parameter.name).strip().isdigit():
                source = str(parameter.value).strip().replace("_", " ")
                if source and source not in sources:
                    sources.append(source)
    if not sources:
        raise ValueError("Echo loot page has no ordinary drop reference")
    return sources


def unique_drops(page, text, items):
    # Use the complete canonical parser so notes, quantities and conditional
    # metadata survive. The scoped section excludes historical equipment.
    source = "{{Infobox Monster}}\n==Drops==\n" + drops_section(text)
    tables = drops_wikitext.parse_all_drop_tables(source)
    if len(tables) != 1:
        raise ValueError("Expected one unique table: " + page)
    spec = drops_tables.build_table_spec(page, tables[0], items)
    if spec.unresolved_items:
        raise ValueError("Unresolved unique items: " + repr(spec.unresolved_items))
    table = drops_tables.build_table_json(spec)
    unique = []
    for entry in table["entries"]:
        item_id, weight, out_of = entry.get("item_id"), entry.get("weight"), entry.get("out_of")
        if not isinstance(item_id, int) or weight != 1 or not isinstance(out_of, int):
            raise ValueError("Unique needs an explicit 1/N rate: " + page)
        notes = " ".join(entry.get("notes") or [])
        guarantee = re.search(r"(\d+)(?:st|nd|rd|th)\s+[^.]*?kill", notes, re.I)
        if not guarantee or int(guarantee.group(1)) != 2 * out_of:
            raise ValueError("Missing or inconsistent first-copy guarantee: " + page)
        unique.append({"itemId": item_id, "rate": out_of,
                       "guarantee": int(guarantee.group(1))})
    if not unique:
        raise ValueError("No unique rewards: " + page)
    return table, unique


def build_encounter_variants(manifest=None, pages=None, items=None):
    manifest = manifest or json.loads(MANIFEST.read_text(encoding="utf-8"))
    pages = pages or json.loads(PAGES.read_text(encoding="utf-8"))
    items = items or drops_tables.ItemIdLookup(items_api.load())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported manifest version")
    bosses = {}
    for boss, anchors in manifest["bosses"].items():
        page = anchors["loot_page"]
        table, uniques = unique_drops(page, pages[page], items)
        bosses[boss] = {
            "profiles": {role: profile_from_page(anchor["page"], pages[anchor["page"]], anchor.get("version"))
                         for role, anchor in anchors["profiles"].items()},
            "normal_sources": normal_sources(pages[page]),
            "unique_table": table,
            "uniques": uniques,
        }
    return {"schema_version": 1, "bosses": bosses}


def render(data):
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def export_encounter_variants(output):
    data = build_encounter_variants()
    with Path(output).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(render(data))
    return len(data["bosses"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=config.DOCS_PATH / "npc-encounter-variants.json")
    args = parser.parse_args()
    print("Exported {} named encounters.".format(export_encounter_variants(args.output)))
