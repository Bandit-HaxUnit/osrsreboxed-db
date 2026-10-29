"""Export reward caskets independently of NPC drop tables (GPL-3.0-or-later).

The reviewed TSV is an authoring input transcribed from the rendered Wiki table,
not generated JSON or a reconstructed wikitext page. See sources/README.md.
All probabilities remain exact fractions until converted to integer weights.

Usage: python -m scripts.drops.reward_caskets --out docs/drops-json/reward-caskets.json
"""

import argparse
import csv
import hashlib
import json
from fractions import Fraction
from math import gcd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("sources") / "beginner-rewards.tsv"
WIKI = "https://oldschool.runescape.wiki/w/Reward_casket_(beginner)"


def load_item_ids(items):
    """Match canonical Wiki names first, excluding notes and cache duplicates."""
    names, wiki_names = {}, {}
    for item in sorted(
        items.values(), key=lambda row: (not row["tradeable_on_ge"], row["id"])
    ):
        if any(
            item.get(flag) for flag in ("duplicate", "noted", "placeholder", "stacked")
        ):
            continue
        names.setdefault(item["name"].casefold(), item["id"])
        if item.get("wiki_name"):
            wiki_names.setdefault(item["wiki_name"].casefold(), item["id"])
    return {**names, **wiki_names}


def build_beginner(source, item_ids):
    """Resolve captured rows; refuse incomplete tables or unresolvable items."""
    with source.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    rates = [Fraction(row["rarity"]) for row in rows]
    if not rows or any(rate <= 0 for rate in rates) or sum(rates) != 1:
        raise ValueError("Reward probabilities must be positive and sum exactly to one")
    denominator = 1
    for rate in rates:
        denominator = denominator * rate.denominator // gcd(denominator, rate.denominator)
    entries, seen = [], set()
    for row, rate in zip(rows, rates):
        if row["name"] in seen:
            raise ValueError("Duplicate reward: " + row["name"])
        seen.add(row["name"])
        if row["noted"] not in ("true", "false") or row["unique"] not in (
            "true", "false"
        ):
            raise ValueError("Invalid boolean in reward source")
        quantity = [int(value) for value in row["quantity"].split("-")]
        if len(quantity) == 1:
            quantity *= 2
        if len(quantity) != 2 or not 0 < quantity[0] <= quantity[1]:
            raise ValueError("Invalid reward quantity")
        item_id = item_ids.get(row["name"].casefold())
        if item_id is None:
            raise ValueError("Unresolved reward item: " + row["name"])
        entries.append(
            {
                "item_id": item_id,
                "name": row["name"],
                "quantity": quantity,
                "weight": int(rate * denominator),
                "rarity_raw": row["rarity"],
                "noted": row["noted"] == "true",
                "unique": row["unique"] == "true",
            }
        )
    return {
        "casket_item_id": 23245,
        "rolls": [1, 3],
        "out_of": denominator,
        "entries": entries,
        "restrictions": {
            "cannot_open_on_entrana": True,
            "unique_minimum_account_age_seconds": 36000,
            "ineligible_unique_replacement": None,
        },
        "milestones": [
            {"completed": 50, "item_id": 30902, "name": "Minor beginner scroll case"},
            {"completed": 100, "item_id": 30904, "name": "Major beginner scroll case"},
            {"completed": 600, "emote": "Explore"},
        ],
    }


def generate(source, items_path, output):
    with items_path.open(encoding="utf-8") as stream:
        item_ids = load_item_ids(json.load(stream))
    payload = {
        "meta": {
            "source": WIKI,
            "source_capture": "2026-10-23 indexed rendered Wiki page; revision unavailable",
            "license": "CC BY-NC-SA 3.0 — Old School RuneScape Wiki contributors",
            "source_sha256": hashlib.sha256(
                source.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
            "items_sha256": hashlib.sha256(
                items_path.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
            "rate_reference": "Wiki cites Mod Tide, 11 October 2019",
            "limits": [
                "The source does not specify replacement behavior for ineligible uniques.",
                "Milestone scroll cases were released 2 July 2025; older caches may lack them.",
                "Milestone cases are conditional unlocks, not per-roll random rewards.",
            ],
        },
        "beginner": build_beginner(source, item_ids),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--items", type=Path, default=ROOT / "docs/items-complete.json")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "docs/drops-json/reward-caskets.json"
    )
    args = parser.parse_args()
    generate(args.source, args.items, args.out)


if __name__ == "__main__":
    main()
