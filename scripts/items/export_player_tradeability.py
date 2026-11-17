"""Export explicit Wiki player-tradeability, preserving exact infobox ID versions.

Unlike the legacy items export, missing Wiki fields are unknown rather than False.
This standalone contract does not change any existing item database fields.
The input digest hashes UTF-8 source text with CRLF normalized to LF, independent of Git checkout settings.
"""

import argparse
import hashlib
import html
import json
import re
import unicodedata
from pathlib import Path

import mwparserfromhell

from scripts.wiki.wikitext_parser import WikitextTemplateParser


def plain(value):
    return " ".join(
        html.unescape(mwparserfromhell.parse(str(value)).strip_code()).split()
    )


def normalized_name(value):
    return " ".join(
        unicodedata.normalize("NFKC", value).replace("_", " ").split()
    ).casefold()


def build_export(pages, input_sha256):
    candidates = {}
    diagnostics = []
    conflicts = set()
    noteability_conflicts = set()
    for page, text in sorted(pages.items()):
        if not isinstance(text, str):
            raise ValueError("Wiki page text must be a string")
        for ordinal, template in enumerate(
            mwparserfromhell.parse(text).filter_templates(), 1
        ):
            if str(template.name).strip().lower() != "infobox item":
                continue
            parser = WikitextTemplateParser(text)
            parser.template = template
            fields = {}
            duplicate = False
            for parameter in template.params:
                key = str(parameter.name).strip().lower()
                if key in fields and re.fullmatch(
                    r"(?:id|itemid|name|tradeable|noteable)\d*", key
                ):
                    diagnostics.append(
                        {
                            "page": page,
                            "template": ordinal,
                            "reason": "duplicate-field",
                            "field": key,
                        }
                    )
                    duplicate = True
                fields[key] = parser.extract_infobox_value(str(parameter.name))
            if duplicate:
                continue
            for key, raw_id in fields.items():
                match = re.fullmatch(r"(?:id|itemid)(\d*)", key)
                if not match:
                    continue
                version = int(match.group(1)) if match.group(1) else None
                suffix = str(version) if version is not None else ""
                # strip_code removes comments, never turns free text into a guessed ID.
                ids = plain(raw_id)
                if version == 0 or not re.fullmatch(r"\d+(?:\s*,\s*\d+)*", ids):
                    diagnostics.append(
                        {
                            "page": page,
                            "template": ordinal,
                            "reason": "malformed-id",
                            "field": key,
                        }
                    )
                    continue
                value = fields.get("tradeable" + suffix, fields.get("tradeable"))
                value = plain(value).lower() if value is not None else None
                if value not in ("yes", "no"):
                    diagnostics.append(
                        {
                            "page": page,
                            "template": ordinal,
                            "reason": "unknown-tradeability",
                            "field": key,
                        }
                    )
                    continue
                # The Wiki's omitted name defaults to the page title. A versioned name wins.
                name = plain(fields.get("name" + suffix, fields.get("name", page)))
                if not name:
                    diagnostics.append(
                        {
                            "page": page,
                            "template": ordinal,
                            "reason": "unknown-name",
                            "field": key,
                        }
                    )
                    continue
                noteable = fields.get("noteable" + suffix, fields.get("noteable"))
                noteable = plain(noteable).lower() if noteable is not None else None
                noteable = noteable == "yes" if noteable in ("yes", "no") else None
                for item_id in map(int, ids.split(",")):
                    row = {
                        "id": item_id,
                        "name": name,
                        "playerTradeable": value == "yes",
                        "noteable": noteable,
                        "sourcePage": page,
                        "sourceVersion": version,
                    }
                    previous = candidates.get(item_id)
                    if previous is not None:
                        if (
                            normalized_name(previous["name"]),
                            previous["playerTradeable"],
                        ) != (normalized_name(name), row["playerTradeable"]):
                            conflicts.add(item_id)
                            diagnostics.append(
                                {
                                    "page": page,
                                    "id": item_id,
                                    "reason": "conflicting-id",
                                    "otherPage": previous["sourcePage"],
                                    "previous": previous,
                                    "candidate": row,
                                }
                            )
                        else:
                            if previous["noteable"] != noteable:
                                noteability_conflicts.add(item_id)
                                previous["noteable"] = None
                                diagnostics.append(
                                    {
                                        "page": page,
                                        "id": item_id,
                                        "reason": "conflicting-noteability",
                                        "otherPage": previous["sourcePage"],
                                    }
                                )
                            diagnostics.append(
                                {
                                    "page": page,
                                    "id": item_id,
                                    "reason": "duplicate-consistent-id",
                                    "otherPage": previous["sourcePage"],
                                }
                            )
                    else:
                        candidates[item_id] = row
                    if item_id in noteability_conflicts:
                        candidates[item_id]["noteable"] = None
    return {
        "schema": 1,
        "input_sha256": input_sha256,
        "rows": [
            candidates[item_id]
            for item_id in sorted(candidates)
            if item_id not in conflicts
        ],
        "diagnostics": sorted(
            diagnostics, key=lambda row: json.dumps(row, sort_keys=True)
        ),
    }


def export_bytes(pages, input_sha256):
    return (
        json.dumps(build_export(pages, input_sha256), ensure_ascii=False, indent=2)
        + "\n"
    ).encode("utf-8")


def export_source_bytes(source):
    normalized = source.replace(b"\r\n", b"\n")
    return export_bytes(json.loads(normalized), hashlib.sha256(normalized).hexdigest())


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=root / "data/items/items-wiki-page-text.json"
    )
    parser.add_argument(
        "--out", type=Path, default=root / "docs/item-player-tradeability.json"
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = args.source.read_bytes()
    output = export_source_bytes(source)
    if args.check:
        if args.out.read_bytes() != output:
            raise SystemExit("Explicit player-tradeability export is stale")
    else:
        args.out.write_bytes(output)
    data = json.loads(output)
    print(
        json.dumps(
            {
                "rows": len(data["rows"]),
                "diagnostics": len(data["diagnostics"]),
                "sha256": hashlib.sha256(output).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
