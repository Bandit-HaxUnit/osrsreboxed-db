"""Regression checks for the monster variant resolver (builders/monsters/variant_resolver.py).

The synthetic pages copy the OSRS Wiki's numbered infobox layout (version1, combat1, id1 ...).
"""

import json
from pathlib import Path

import config
from builders.monsters import variant_resolver as vr

WOLF_LIKE = """{{Infobox Monster
|version1 = Level 11
|version2 = Level 25
|name = Wolf
|id1 = 116
|id2 = 117
|combat1 = 11
|combat2 = 25
|hitpoints1 = 10
|hitpoints2 = 34
|att1 = 10
|att2 = 20
|def1 = 10
|def2 = 22
|str1 = 10
|str2 = 16
|mage = 1
|range = 1
}}"""

# Two infobox blocks; each id is listed once, under its own variant.
TWO_BLOCKS = """{{Infobox Monster
|version1 = Hostile
|version2 = Passive
|name = Knight
|id1 = 501
|id2 = 502
|combat = 33
|hitpoints = 42
}}
{{Infobox Monster
|version1 = Hostile, female
|name = Knight
|id1 = 503
|combat = 33
|hitpoints = 42
}}"""

# Same stats for every variant, and no id is listed for any of them.
FAMILY = """{{Infobox Monster
|version1 = Level 24, 1
|version2 = Level 24, 2
|version3 = Level 24, 3
|name = Zombie
|combat1 = 24
|combat2 = 24
|combat3 = 24
|hitpoints1 = 30
|hitpoints2 = 30
|hitpoints3 = 30
}}"""

CACHE_LEVEL_25 = {"combatLevel": 25, "stats": [20, 22, 16, 34, 1, 1]}
CACHE_LEVEL_11 = {"combatLevel": 11, "stats": [10, 10, 10, 10, 1, 1]}


def test_numbered_variants_are_read_per_version():
    variants = vr.page_variants("Wolf", WOLF_LIKE)
    assert [(v.version_number, v.version_name) for v in variants] == [
        ("1", "Level 11"),
        ("2", "Level 25"),
    ]
    assert variants[1].stats[:2] == (25.0, 34.0)
    assert variants[1].ids == (117,)


def test_id_listed_by_one_variant_resolves_to_that_variant():
    raw = {"Wolf": WOLF_LIKE}
    index = vr.build_index(raw)
    variant, reason = vr.resolve(
        117, "Wolf", vr.cache_stats(CACHE_LEVEL_25), index, raw
    )
    assert variant is not None and variant.version_number == "2"
    assert "one infobox lists this id" in reason


def test_unlisted_id_takes_the_variant_whose_stats_match_the_cache():
    # 116 is in no id list here, so the page named after the NPC decides by cache stats.
    raw = {"Wolf": WOLF_LIKE.replace("|id1 = 116\n", "")}
    index = vr.build_index(raw)
    variant, _ = vr.resolve(116, "Wolf", vr.cache_stats(CACHE_LEVEL_25), index, raw)
    assert variant is not None and variant.version_number == "2"
    assert variant.version_name == "Level 25"


def test_two_blocks_keep_each_id_on_its_own_variant():
    raw = {"Knight": TWO_BLOCKS}
    index = vr.build_index(raw)
    cache = {"combatLevel": 33, "stats": [1, 1, 1, 42, 1, 1]}
    passive, _ = vr.resolve(502, "Knight", vr.cache_stats(cache), index, raw)
    hostile, _ = vr.resolve(501, "Knight", vr.cache_stats(cache), index, raw)
    assert passive.version_name == "Passive" and passive.block_index == 1
    assert hostile.version_name == "Hostile" and hostile.block_index == 1
    female, _ = vr.resolve(503, "Knight", vr.cache_stats(cache), index, raw)
    assert female.version_name == "Hostile, female" and female.block_index == 2


def test_identical_family_uses_the_first_variant_and_says_so():
    raw = {"Zombie": FAMILY}
    index = vr.build_index(raw)
    variant, reason = vr.resolve(
        53,
        "Zombie",
        vr.cache_stats({"combatLevel": 24, "stats": [1, 1, 1, 30, 1, 1]}),
        index,
        raw,
    )
    assert variant is not None and variant.version_number == "1"
    assert reason.startswith("ambiguous:")


def test_no_stats_match_leaves_the_npc_unresolved():
    raw = {"Wolf": WOLF_LIKE.replace("|id1 = 116\n", "")}
    index = vr.build_index(raw)
    cache = {"combatLevel": 99, "stats": [1, 1, 1, 99, 1, 1]}
    variant, reason = vr.resolve(116, "Wolf", vr.cache_stats(cache), index, raw)
    assert variant is None
    assert "no variant matches" in reason


def test_committed_output_uses_the_level_25_wolf_for_116():
    # Regression on the regenerated output: 116 was built from the Level 11 wolf before the fix.
    entry = json.loads(
        Path(config.DOCS_PATH / "monsters-json" / "116.json").read_text(
            encoding="utf-8"
        )
    )
    assert entry["wiki_url"].endswith("/Wolf#Level_25")
    assert entry["combat_level"] == 25
    assert entry["hitpoints"] == 34
