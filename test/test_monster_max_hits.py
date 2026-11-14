import mwparserfromhell
import pytest

from builders.monsters import infobox_cleaner
from builders.monsters.build_monster import BuildMonster

KILLERWATT = (
    "8 ([[Ranged]]), 6 ([[Melee]]), 15 ([[Ranged]]/[[Melee]]; without [[insulated boots]])"
)


def parse_builder(properties):
    builder = BuildMonster.__new__(BuildMonster)
    builder.monster_dict = {}
    builder.monster_name = "Max hit fixture"
    builder.wikitext_found_using = "name"
    builder.infobox_version_number = None
    builder.template = mwparserfromhell.parse(
        "{{Infobox Monster|" + properties + "}}"
    ).filter_templates()[0]
    builder.populate_monster_properties_from_wiki_data()
    return builder


def test_killerwatt_keeps_every_listed_max_hit_with_its_label():
    # Wiki (Killerwatt infobox): one max hit per style, and a higher one without insulated boots.
    assert infobox_cleaner.max_hits(KILLERWATT) == [
        {"value": "8", "label": "Ranged", "max_hit": 8},
        {"value": "6", "label": "Melee", "max_hit": 6},
        {"value": "15", "label": "Ranged/Melee; without insulated boots", "max_hit": 15},
    ]


def test_builder_keeps_the_list_off_the_combat_export():
    builder = parse_builder("max hit = " + KILLERWATT)
    # The combat export's single integer is unchanged (the first listed value).
    assert builder.monster_dict["max_hit"] == 8
    assert "max_hits" not in builder.monster_dict
    assert [entry["max_hit"] for entry in builder.max_hits] == [8, 6, 15]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("", []),
        ("25", [{"value": "25", "label": None, "max_hit": 25}]),
        ("0-17 (Magic)", [{"value": "0-17", "label": "Magic", "max_hit": 17}]),
        (
            "{{plainlist|\n* 30 (auto attack)\n* 60 (special)\n}}",
            [
                {"value": "30", "label": "auto attack", "max_hit": 30},
                {"value": "60", "label": "special", "max_hit": 60},
            ],
        ),
        (
            "41 (Melee, typeless), 32 ([[Magic]])",
            [
                {"value": "41", "label": "Melee, typeless", "max_hit": 41},
                {"value": "32", "label": "Magic", "max_hit": 32},
            ],
        ),
        # Forms that need the Wiki's own reading keep their text and no number.
        (
            "22 ([[Melee]]), 50+ ([[Dragonfire]])",
            [
                {"value": "22", "label": "Melee", "max_hit": 22},
                {"value": "50+", "label": "Dragonfire", "max_hit": None},
            ],
        ),
        (
            "42 (x2) ([[Melee]]), 50/60 (Soul Siphon)",
            [
                {"value": "42 (x2)", "label": "Melee", "max_hit": None},
                {"value": "50/60", "label": "Soul Siphon", "max_hit": None},
            ],
        ),
        (
            "32-43 ([[Melee]]){{efn|name=def|Scales linearly.}}, 35 (axes)",
            [
                {"value": "32-43", "label": "Melee", "max_hit": 43},
                {"value": "35", "label": "axes", "max_hit": 35},
            ],
        ),
        (
            "50/60 ([[Melee]]), Increased by 20% if praying wrongly",
            [{"value": "50/60", "label": "Melee", "max_hit": None}],
        ),
        ("Varies", []),
    ],
)
def test_max_hits_parses_lists_ranges_and_plainlists(value, expected):
    assert infobox_cleaner.max_hits(value) == expected


def test_export_lists_only_monsters_with_more_than_one_max_hit():
    from scripts.monsters.max_hits import build_max_hits

    values = {"469": KILLERWATT, "2": "12", "9": KILLERWATT}

    class Monster:
        def __init__(self, key):
            self.key = key

        def preprocessing(self):
            return self.key != "9", "missing source"

        def populate_monster(self):
            builder = parse_builder("max hit = " + values[self.key])
            self.monster_dict = {"id": int(self.key), "name": "Fixture", **builder.monster_dict}
            self.max_hits = builder.max_hits

    class Source:
        def _get_entity_id_list(self):
            return ["469", "9", "2"]

        def _build_entity(self, key):
            return Monster(key)

    result = build_max_hits(Source())
    assert result == {
        "schema_version": 1,
        "npcs": {
            "469": {
                "name": "Fixture",
                "max_hits": infobox_cleaner.max_hits(KILLERWATT),
            }
        },
    }
