"""Real-source contracts for the original easy to master clue reward pools."""

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from scripts.drops import reward_caskets

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "scripts/drops/sources"
TIERS = ("easy", "medium", "hard", "elite", "master")
# Wiki revision IDs of the captured sources (see sources/README.md).
REVISIONS = {
    "easy": 15358923,
    "medium": 15358924,
    "hard": 15360008,
    "elite": 15360009,
    "master": 15370773,
}


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
        ("easy", 211, 20546, [2, 4], None),
        ("medium", 192, 20545, [3, 5], None),
        # 235 source rows: the mega-rare super attack/strength/defence trio is one outcome.
        ("hard", 233, 20544, [4, 6], None),
        ("elite", 182, 20543, [4, 6], "1/35"),
        ("master", 173, 19836, [5, 7], "1/15"),
    ],
)
def test_real_source_exact_pools(tier, count, item_id, rolls, mimic):
    table = build(tier)
    assert len(table["entries"]) == count
    assert table["casket_item_id"] == item_id
    assert table["rolls"] == rolls
    assert table.get("mimic_chance") == mimic
    assert ("mimic_chance" in table) == (mimic is not None)
    assert sum(row["weight"] for row in table["entries"]) == table["out_of"]
    assert all(row["weight"] > 0 for row in table["entries"])
    assert all(
        row["section"] != "Tertiary" and "Mimic" not in row["section"]
        for row in table["entries"]
    )


@pytest.mark.parametrize("tier", ["easy", "medium"])
def test_entrana_pool_is_not_merged_into_the_normal_pool(tier):
    # Hard has no Entrana section in the captured revision.
    source = (SOURCES / (tier + "-rewards.wikitext")).read_text(encoding="utf-8")
    assert "==Rewards on Entrana==" in source
    table = build(tier)
    assert all("Entrana" not in row["section"] for row in table["entries"])
    without_entrana = source.split("==Rewards on Entrana==", 1)[0]
    assert build(tier, without_entrana) == table


@pytest.mark.parametrize("tier", ["elite", "master"])
def test_mimic_sentence_is_required_for_elite_and_master(tier):
    source = (SOURCES / (tier + "-rewards.wikitext")).read_text(encoding="utf-8")
    stripped = source.replace("There is also a", "There is a", 1)
    with pytest.raises(ValueError, match="Missing clue reward source configuration"):
        build(tier, stripped)


def test_mimic_sentence_is_rejected_for_lower_tiers():
    source = (SOURCES / "easy-rewards.wikitext").read_text(encoding="utf-8")
    extra = source.replace(
        "==Rewards==\n",
        "==Rewards==\nThere is also a 1/35 chance of the reward casket being a "
        "[[mimic]].\n",
        1,
    )
    with pytest.raises(ValueError, match="Mimic"):
        build("easy", extra)


def test_hard_mega_rare_potion_trio_is_one_joint_outcome():
    table = build("hard")
    trio = [row for row in table["entries"] if "items" in row]
    assert len(trio) == 1
    (trio,) = trio
    assert "item_id" not in trio and "name" not in trio
    assert [item["name"] for item in trio["items"]] == [
        "Super attack(4)",
        "Super strength(4)",
        "Super defence(4)",
    ]
    assert [item["item_id"] for item in trio["items"]] == [2436, 2440, 2442]
    assert all(item["quantity"] == [5, 5] and item["noted"] for item in trio["items"])
    assert trio["section"] == "Mega-rare table - Hard clues"
    assert Fraction(trio["weight"], table["out_of"]) == Fraction(1, 16250)
    names = {row.get("name") for row in table["entries"]}
    assert not names & {"Super attack(4)", "Super strength(4)", "Super defence(4)"}


TRIO_DEFENCE = (
    "|name=Super defence(4)|quantity=5 (noted)|rarity=1/{{#expr:1/( 1/13 * 1/125 * "
)


@pytest.mark.parametrize(
    "change,error",
    [
        (
            lambda source: source.replace(
                TRIO_DEFENCE + "1/10 )", TRIO_DEFENCE + "1/9 )", 1
            ),
            "Joint reward",
        ),
        (
            lambda source: source.replace(
                "|name=Super defence(4)|", "|name=Super restore(4)|", 1
            ),
            "Joint reward",
        ),
        (lambda source: source.replace("together with", "or"), "sum exactly"),
    ],
)
def test_joint_outcomes_fail_closed(change, error):
    source = (SOURCES / "hard-rewards.wikitext").read_text(encoding="utf-8")
    changed = change(source)
    assert changed != source
    with pytest.raises(ValueError, match=error):
        build("hard", changed)


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
            "easy",
            [
                ("Minor easy scroll case", "Always"),
                ("Major easy scroll case", "Always"),
                ("Clue scroll (master)", "1/50"),
                ("Large spade", "Always"),
            ],
        ),
        (
            "medium",
            [
                ("Minor medium scroll case", "Always"),
                ("Major medium scroll case", "Always"),
                ("Clue scroll (master)", "1/30"),
                ("Clueless scroll", "always"),
            ],
        ),
        (
            "hard",
            [
                ("Clue scroll (master)", "1/15"),
                ("Minor hard scroll case", "Always"),
                ("Major hard scroll case", "Always"),
                ("Uri transform", "always"),
            ],
        ),
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
    master_clue = next(
        (row for row in table["tertiary"] if row["name"] == "Clue scroll (master)"),
        None,
    )
    if master_clue is not None:
        assert master_clue["item_id"] == 19835
        assert Fraction(master_clue["probability"]) == Fraction(
            master_clue["rarity_raw"]
        )


def test_uri_transform_is_an_emote_unlock_not_an_item():
    table = build("hard")
    uri = next(row for row in table["tertiary"] if row["name"] == "Uri transform")
    assert "item_id" not in uri
    assert uri["unlock"] == "emote"
    assert "300th completed hard clue" in " ".join(uri["notes"])
    assert all("unlock" not in row for row in table["tertiary"] if row is not uri)


def test_other_unresolved_tertiary_names_still_fail_closed():
    source = (SOURCES / "hard-rewards.wikitext").read_text(encoding="utf-8")
    changed = source.replace("|name=Uri transform|", "|name=Uri dance|", 1)
    with pytest.raises(ValueError, match="Unresolved reward item"):
        build("hard", changed)


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
    assert list(payload["tables"]) == list(TIERS)
    assert list(payload["meta"]["sources"]) == list(TIERS)
    for tier, source in payload["meta"]["sources"].items():
        text = (SOURCES / (tier + "-rewards.wikitext")).read_text(encoding="utf-8")
        assert source["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert source["revision"] == REVISIONS[tier]
    assert "CC BY-NC-SA" in payload["meta"]["license"]


def test_invalid_input_preserves_previous_export(tmp_path):
    from scripts.drops.clue_caskets import generate

    source_root = tmp_path / "sources"
    source_root.mkdir()
    for tier in TIERS:
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
        for tier in TIERS:
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
