"""Export Wiki ItemSpawnLine coordinates without guessing runtime conditions or timer units.

Item infobox respawn values are ticks; per-coordinate respawn is free text in Module:Map.
Keep them separate. Consumers decide explicitly when an infobox default is applicable.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from scripts.wiki.wikitext_parser import extract_wikitext_template

ROOT = Path(__file__).resolve().parents[2]
KNOWN_ROW_PARAMETERS = {
    "name",
    "location",
    "members",
    "plane",
    "mapID",
    "zoom",
    "leagueRegion",
    "trailblazerRegion",
    "uk",
}


def _value(template, name, default=""):
    return str(template.get(name).value).strip() if template.has(name) else default


def _positive_integer(value):
    return int(value) if re.fullmatch(r"[1-9][0-9]*", value) else None


def _versions(text, title):
    versions = []
    for box in extract_wikitext_template(text, "infobox item"):
        for param in box.params:
            key = str(param.name).strip()
            match = re.fullmatch(r"id([0-9]*)", key)
            if not match:
                continue
            suffix = match[1]
            raw_id = str(param.value).strip()
            versions.append(
                {
                    "id": int(raw_id) if re.fullmatch(r"[0-9]+", raw_id) else None,
                    "name": _value(box, "name" + suffix, _value(box, "name", title)),
                    "respawn_raw": _value(
                        box, "respawn" + suffix, _value(box, "respawn")
                    ),
                    "version": suffix,
                }
            )
    return versions


def parse_pages(pages):
    """All positional spawn arguments survive, including malformed/unresolved ones."""
    rows = []
    for title, text in sorted(pages.items()):
        if not isinstance(text, str):
            continue
        versions = (
            _versions(text, title) if re.search("ItemSpawnLine", text, re.I) else []
        )
        for index, template in enumerate(
            extract_wikitext_template(text, "itemspawnline")
        ):
            raw_parameters = {
                str(p.name).strip(): str(p.value).strip() for p in template.params
            }
            row_name = _value(template, "name", title)
            matching = [v for v in versions if v["name"] == row_name]
            candidates = matching or (versions if row_name == title else [])
            ids = sorted({v["id"] for v in candidates if v["id"] is not None})
            item_id = ids[0] if len(ids) == 1 else None
            defaults = sorted(
                {v["respawn_raw"] for v in candidates if v["id"] == item_id}
            )
            default_raw = defaults[0] if len(defaults) == 1 else ""
            page_ticks = _positive_integer(default_raw)
            member_raw = _value(template, "members", "No")
            members = {"yes": True, "no": False}.get(member_raw.lower())
            plane_raw = _value(template, "plane", "0")
            unknown_parameters = sorted(
                k
                for k in raw_parameters
                if not k.isdigit() and k not in KNOWN_ROW_PARAMETERS
            )
            for argument, raw in raw_parameters.items():
                if not argument.isdigit():
                    continue
                reasons = []
                coordinate = re.fullmatch(r"([0-9]+)\s*,\s*([0-9]+)(.*)", raw)
                qualifiers = {}
                if coordinate:
                    for part in coordinate[3].strip(",").split(","):
                        if part.strip():
                            key, separator, value = part.partition(":")
                            qualifiers[key.strip()] = (
                                value.strip() if separator else None
                            )
                else:
                    reasons.append("unparsed-coordinate")
                actual_plane = qualifiers.get("plane", plane_raw)
                plane = (
                    int(actual_plane)
                    if isinstance(actual_plane, str)
                    and actual_plane in {"0", "1", "2", "3"}
                    else None
                )
                quantity_raw = qualifiers.get("qty", "1")
                quantity = (
                    _positive_integer(quantity_raw)
                    if isinstance(quantity_raw, str)
                    else None
                )
                if item_id is None:
                    reasons.append("ambiguous-item-id")
                if page_ticks is None:
                    reasons.append("missing-positive-infobox-respawn")
                if members is None:
                    reasons.append("unresolved-members")
                if plane is None:
                    reasons.append("unresolved-plane")
                if quantity is None:
                    reasons.append("unresolved-quantity")
                if "respawn" in qualifiers:
                    reasons.append("untyped-tile-respawn")
                if set(qualifiers) - {"qty", "plane", "respawn"}:
                    reasons.append("coordinate-condition-or-unknown-qualifier")
                if unknown_parameters:
                    reasons.append("row-selection-or-unknown-parameter")
                rows.append(
                    {
                        "page": title,
                        "page_sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "row_index": index,
                        "argument": argument,
                        "name": row_name,
                        "id": item_id,
                        "candidate_ids": ids,
                        "location": _value(template, "location"),
                        "x": int(coordinate[1]) if coordinate else None,
                        "y": int(coordinate[2]) if coordinate else None,
                        "plane": plane,
                        "members": members,
                        "quantity": quantity,
                        "infobox_respawn_ticks": page_ticks,
                        "infobox_respawn_raw": default_raw,
                        "tile_respawn_raw": qualifiers.get("respawn"),
                        "coordinate_raw": raw,
                        "coordinate_qualifiers": qualifiers,
                        "row_parameters": {
                            k: v for k, v in raw_parameters.items() if not k.isdigit()
                        },
                        "unresolved_reasons": sorted(reasons),
                    }
                )
    return rows


def build_export(raw_bytes):
    pages = json.loads(raw_bytes)
    return {
        "schema": 1,
        "input_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "timer_policy": "Infobox respawn is ticks; tile overrides remain untyped raw text. No automatic inheritance is asserted.",
        "rows": parse_pages(pages),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "data/items/items-wiki-page-text.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/ground-item-spawns.json"
    )
    args = parser.parse_args()
    result = build_export(args.input.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    print(
        f"Exported {len(result['rows'])} spawn arguments from {result['input_sha256']}"
    )


if __name__ == "__main__":
    main()
