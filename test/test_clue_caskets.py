"""Real-source contracts for the original elite/master clue reward pools."""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from scripts.drops import reward_caskets

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "scripts/drops/sources"


def build(tier, text=None, ids=None):
    from scripts.drops.clue_caskets import build_casket

    if ids is None:
        ids = reward_caskets.load_item_ids(
            json.loads((ROOT / "docs/items-complete.json").read_text(encoding="utf-8"))
        )
    return build_casket(
        (
            text
            if text is not None
            else (SOURCES / (tier + "-rewards.wikitext")).read_text(encoding="utf-8")
        ),
        tier,
        ids,
    )


@pytest.mark.parametrize(
    "tier,count,item_id,rolls,mimic",
    [
        ("elite", 182, 20543, [4, 6], "1/35"),
        ("master", 173, 19836, [5, 7], "1/15"),
    ],
)
def test_real_source_exact_pools(tier, count, item_id, rolls, mimic):
    table = build(tier)
    assert len(table["entries"]) == count
    assert table["casket_item_id"] == item_id
    assert table["rolls"] == rolls
    assert table["mimic_chance"] == mimic
    assert sum(row["weight"] for row in table["entries"]) == table["out_of"]
    assert all(row["weight"] > 0 for row in table["entries"])
    assert all(
        row["section"] != "Tertiary" and "Mimic" not in row["section"]
        for row in table["entries"]
    )


def test_underlying_probabilities_ignore_display_rounding_and_keep_duplicate_coins():
    table = build("elite")
    coins = [row for row in table["entries"] if row["item_id"] == 995]
    assert len(coins) == 2
    assert [row["quantity"] for row in coins] == [[20000, 30000], [10000, 15000]]
    assert [Fraction(row["weight"], table["out_of"]) for row in coins] == [
        Fraction(24, 775),
        Fraction(42, 3875),
    ]
    assert all("round 1" in row["rarity_raw"] for row in coins)
    brew = next(row for row in table["entries"] if row["name"] == "Saradomin brew(4)")
    assert brew["noted"] is True
    assert brew["quantity"] == [30, 30]


@pytest.mark.parametrize(
    "tier,expected",
    [
        (
            "elite",
            [
                ("Clue scroll (master)", "1/5"),
                ("Minor elite scroll case", "Always"),
                ("Major elite scroll case", "Always"),
                ("Heavy casket", "always"),
            ],
        ),
        (
            "master",
            [
                ("Bloodhound", "1/1000"),
                ("Scroll sack", "always"),
                ("Minor master scroll case", "Always"),
                ("Major master scroll case", "Always"),
            ],
        ),
    ],
)
def test_tertiary_conditions_stay_outside_the_normal_pool(tier, expected):
    table = build(tier)
    assert [(row["name"], row["rarity_raw"]) for row in table["tertiary"]] == expected
    minor = next(row for row in table["tertiary"] if row["name"].startswith("Minor"))
    assert "did not open it before" in " ".join(minor["notes"])
    assert "lost the item" in " ".join(minor["notes"])
    if tier == "elite":
        assert "X Marks the Spot" in " ".join(table["tertiary"][0]["notes"])


@pytest.mark.parametrize(
    "change,error",
    [
        (
            lambda source: source.replace(
                "|name=Dragon full helm ornament kit", "|name=Unknown reward item", 1
            ),
            "Unresolved",
        ),
        (
            lambda source: source.replace(
                "|quantity=1|rarity=", "|quantity=1; 3|rarity=", 1
            ),
            "quantity",
        ),
        (lambda source: source.replace("1/25 * 1/51", "1/24 * 1/51", 1), "sum exactly"),
        (lambda source: source.replace("1/25 * 1/51", "bad()", 1), "probability"),
    ],
)
def test_unsupported_or_incomplete_source_fails_closed(change, error):
    source = (SOURCES / "elite-rewards.wikitext").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        build("elite", change(source))


def test_generation_is_deterministic_and_records_source_hashes(tmp_path):
    from scripts.drops.clue_caskets import generate

    first, second = tmp_path / "a.json", tmp_path / "b.json"
    for output in (first, second):
        generate(SOURCES, ROOT / "docs/items-complete.json", output)
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert set(payload["tables"]) == {"elite", "master"}
    assert all(len(row["sha256"]) == 64 for row in payload["meta"]["sources"].values())
    assert "CC BY-NC-SA" in payload["meta"]["license"]


def test_invalid_input_preserves_previous_export(tmp_path):
    from scripts.drops.clue_caskets import generate

    source_root = tmp_path / "sources"
    source_root.mkdir()
    for tier in ("elite", "master"):
        text = (SOURCES / (tier + "-rewards.wikitext")).read_text(encoding="utf-8")
        if tier == "master":
            text = text.replace("|name=Bloodhound|", "|name=Unresolved pet|", 1)
        (source_root / (tier + "-rewards.wikitext")).write_text(text, encoding="utf-8")
    output = tmp_path / "retained.json"
    output.write_bytes(b"previous valid artifact")
    with pytest.raises(ValueError, match="Unresolved reward item"):
        generate(source_root, ROOT / "docs/items-complete.json", output)
    assert output.read_bytes() == b"previous valid artifact"


def test_lf_and_crlf_inputs_produce_identical_lf_export(tmp_path):
    from scripts.drops.clue_caskets import generate

    outputs = []
    for label, newline in (("lf", "\n"), ("crlf", "\r\n")):
        source_root = tmp_path / label
        source_root.mkdir()
        for tier in ("elite", "master"):
            text = (SOURCES / (tier + "-rewards.wikitext")).read_text(encoding="utf-8")
            (source_root / (tier + "-rewards.wikitext")).write_bytes(
                text.replace("\n", newline).encode("utf-8")
            )
        items = source_root / "items.json"
        item_text = (ROOT / "docs/items-complete.json").read_text(encoding="utf-8")
        items.write_bytes(item_text.replace("\n", newline).encode("utf-8"))
        output = source_root / "output.json"
        generate(source_root, items, output)
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]
    assert b"\r\n" not in outputs[0]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1/{{#expr:1/(24/25 * 1/31) round 1}}", Fraction(24, 775)),
        ("1/1000", Fraction(1, 1000)),
        ("1/{{#expr:1/(22/23 * 2/29 * 21/22 * 1/12) round 1}}", Fraction(7, 1334)),
    ],
)
def test_exact_probability_uses_source_branch_factors(raw, expected):
    from scripts.drops.clue_caskets import exact_probability

    assert exact_probability(raw) == expected
