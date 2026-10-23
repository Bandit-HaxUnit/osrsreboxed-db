"""Export original elite/master rewards from captured Wiki source (GPL-3.0-or-later).

Unlike displayed denominators, the branch factors inside #expr are exact. The
trailing `round 1` formats a reciprocal denominator for the Wiki table; it must
not turn a game probability into its rounded display approximation.
"""

import argparse
import ast
import hashlib
import json
import re
import sys
from fractions import Fraction
from math import gcd
from pathlib import Path

import mwparserfromhell as mw

from scripts.drops.drops_wikitext import parse_inline_note_fields
from scripts.drops.reward_caskets import ROOT, load_item_ids

SOURCES = Path(__file__).with_name("sources")
TIERS = ("elite", "master")


def _arithmetic(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return Fraction(str(node.value))
    # Python3.7 parses numeric literals as Num rather than Constant.
    if (
        sys.version_info < (3, 8)
        and isinstance(node, ast.Num)
        and type(node.n) in (int, float)
    ):
        return Fraction(str(node.n))
    if isinstance(node, ast.BinOp):
        left, right = _arithmetic(node.left), _arithmetic(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
    raise ValueError("Unsupported reward probability expression")


def exact_probability(raw):
    """Evaluate only arithmetic, retaining the unrounded source branch factors."""
    code = mw.parse(raw)
    try:
        for template in reversed(code.filter_templates()):
            name = str(template.name).strip()
            if not name.lower().startswith("#expr:") or template.params:
                raise ValueError("Unsupported reward probability template")
            expression = name.split(":", 1)[1]
            expression = re.sub(r"\s+round\s+1\s*$", "", expression, flags=re.I)
            value = _arithmetic(ast.parse(expression.strip(), mode="eval").body)
            code.replace(template, "({}/{})".format(value.numerator, value.denominator))
        result = _arithmetic(ast.parse(str(code).strip(), mode="eval").body)
        if not 0 < result <= 1:
            raise ValueError("Reward probability outside (0, 1]")
        return result
    except (
        ValueError,
        SyntaxError,
        TypeError,
        ZeroDivisionError,
        OverflowError,
    ) as exc:
        raise ValueError("Invalid reward probability: " + raw) from exc


def _field(template, key, default=None):
    return str(template.get(key).value).strip() if template.has(key) else default


def _entry(template, section, item_ids):
    name = _field(template, "name", "")
    item_id = item_ids.get(name.casefold())
    if item_id is None:
        raise ValueError("Unresolved reward item: " + name)
    quantity_raw = _field(template, "quantity", "")
    match = re.fullmatch(r"(\d+)(?:-(\d+))?(\s+\(noted\))?", quantity_raw)
    if not match:
        raise ValueError("Unsupported reward quantity: " + quantity_raw)
    minimum, maximum = int(match[1]), int(match[2] or match[1])
    if not 0 < minimum <= maximum:
        raise ValueError("Invalid reward quantity: " + quantity_raw)
    entry = {
        "item_id": item_id,
        "name": name,
        "quantity": [minimum, maximum],
        "noted": bool(match[3]),
        "section": section,
        "rarity_raw": _field(template, "rarity", ""),
    }
    notes = parse_inline_note_fields(
        *[
            _field(template, key, "")
            for key in ("namenotes", "quantitynotes", "raritynotes")
        ]
    )
    if notes:
        entry["notes"] = notes
    return entry


def build_casket(source, tier, item_ids):
    if tier not in TIERS:
        raise ValueError("Unsupported clue tier: " + tier)
    code = mw.parse(source)
    infobox = next(
        (
            node
            for node in code.filter_templates(recursive=False)
            if str(node.name).strip().casefold() == "infobox item"
        ),
        None,
    )
    rolls = re.search(
        tier + r" clues generate a minimum of (\d+) rewards and a maximum of (\d+)",
        source,
        re.I,
    )
    mimic = re.search(
        r"There is also a (\d+/\d+) chance of the reward casket being a \[\[mimic\]\]",
        source,
        re.I,
    )
    if infobox is None or not rolls or not mimic:
        raise ValueError("Missing clue reward source configuration")
    item_id = _field(infobox, "id", "")
    if not item_id.isdigit() or not 0 < int(rolls[1]) <= int(rolls[2]):
        raise ValueError("Invalid clue reward source configuration")
    entries, rates, tertiary = [], [], []
    active, section, excluded_level, tertiary_level = False, "", None, None
    for node in code.nodes:
        if isinstance(node, mw.nodes.Heading):
            title = str(node.title).strip()
            if node.level == 2:
                active = title.casefold() == "rewards"
            if excluded_level is not None and node.level <= excluded_level:
                excluded_level = None
            if tertiary_level is not None and node.level <= tertiary_level:
                tertiary_level = None
            if active:
                section = title
                if "mimic" in title.casefold():
                    excluded_level = node.level
                if title.casefold() == "tertiary":
                    tertiary_level = node.level
        if (
            not active
            or excluded_level is not None
            or not isinstance(node, mw.nodes.Template)
        ):
            continue
        if str(node.name).strip().casefold() != "dropslinereward":
            continue
        entry = _entry(node, section, item_ids)
        if tertiary_level is not None:
            if entry["rarity_raw"].casefold() != "always":
                entry["probability"] = str(exact_probability(entry["rarity_raw"]))
            elif not entry.get("notes"):
                raise ValueError(
                    "Unconditional tertiary reward lacks eligibility evidence"
                )
            tertiary.append(entry)
        else:
            rates.append(exact_probability(entry["rarity_raw"]))
            entries.append(entry)
    if not entries or sum(rates) != 1:
        raise ValueError("Clue reward probabilities must sum exactly to one")
    denominator = 1
    for rate in rates:
        denominator = (
            denominator // gcd(denominator, rate.denominator) * rate.denominator
        )
    for entry, rate in zip(entries, rates):
        entry["weight"] = int(rate * denominator)
    return {
        "casket_item_id": int(item_id),
        "rolls": [int(rolls[1]), int(rolls[2])],
        "mimic_chance": str(exact_probability(mimic[1])),
        "out_of": denominator,
        "entries": entries,
        "tertiary": tertiary,
    }


def generate(sources, items_path, output):
    # Universal-newline reads make provenance stable across Git checkout modes.
    item_text = items_path.read_text(encoding="utf-8")
    item_ids = load_item_ids(json.loads(item_text))
    payload = {
        "schema_version": 1,
        "meta": {
            "sources": {},
            "license": "CC BY-NC-SA 3.0 — Old School RuneScape Wiki contributors",
            "items_sha256": hashlib.sha256(item_text.encode("utf-8")).hexdigest(),
            "hash_encoding": "UTF-8 with LF newlines",
            "probabilities": "Exact source branch factors before Wiki display rounding",
            "tertiary": "Separate from per-roll pools; notes require explicit eligibility handling",
        },
        "tables": {},
    }
    for tier in TIERS:
        path = sources / (tier + "-rewards.wikitext")
        source_text = path.read_text(encoding="utf-8")
        payload["tables"][tier] = build_casket(source_text, tier, item_ids)
        payload["meta"]["sources"][tier] = {
            "url": "https://oldschool.runescape.wiki/w/Reward_casket_(" + tier + ")",
            "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument("--items", type=Path, default=ROOT / "docs/items-complete.json")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "docs/drops-json/clue-caskets.json"
    )
    args = parser.parse_args()
    generate(args.sources, args.items, args.out)


if __name__ == "__main__":
    main()
