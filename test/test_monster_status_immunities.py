import mwparserfromhell
import pytest

from builders.monsters.build_monster import BuildMonster


def parse_status(properties, version=None):
    return parse_builder(properties, version).monster_dict


def parse_builder(properties, version=None):
    builder = BuildMonster.__new__(BuildMonster)
    builder.monster_dict = {}
    builder.monster_name = "Status fixture"
    builder.wikitext_found_using = "name"
    builder.infobox_version_number = version
    builder.template = mwparserfromhell.parse(
        "{{Infobox Monster|" + properties + "}}"
    ).filter_templates()[0]
    builder.populate_monster_properties_from_wiki_data()
    return builder


@pytest.mark.parametrize(
    "properties, expected",
    [
        ("poisonresistance=0|venomresistance=Poison", (False, True)),
        ("poisonresistance=100|venomresistance=100", (True, True)),
        ("poisonresistance=200|venomresistance=200", (True, True)),
        ("poisonresistance=0|venomresistance=0", (False, False)),
        ("immunepoison=Yes|immunevenom=Yes", (True, True)),
        (
            "poisonresistance=0|venomresistance=0|immunepoison=Yes|immunevenom=Yes",
            (False, False),
        ),
    ],
)
def test_current_resistance_fields_and_legacy_aliases(properties, expected):
    result = parse_status(properties)
    assert (result["immune_poison"], result["immune_venom"]) == expected


def test_versioned_resistance_wins_over_shared_and_legacy_values():
    result = parse_status(
        "poisonresistance=100|venomresistance=100|"
        "poisonresistance2=0|venomresistance2=Poison|"
        "immunepoison2=Yes|immunevenom2=No",
        version=2,
    )
    assert result["immune_poison"] is False
    assert result["immune_venom"] is True


def test_partial_resistance_is_not_falsely_exported_as_full_immunity():
    result = parse_status("poisonresistance=50|venomresistance=25")
    assert result["immune_poison"] is False
    assert result["immune_venom"] is False


def test_dedicated_export_uses_canonical_builder_and_excludes_unresolved_source():
    from scripts.monsters.status_immunities import build_status_immunities

    class Monster:
        def __init__(self, key):
            self.key = key

        def preprocessing(self):
            return self.key != "9", "missing source"

        def populate_monster(self):
            self.monster_dict = {
                "id": int(self.key),
                "name": "Fixture",
                **parse_status("poisonresistance=0|venomresistance=Poison"),
            }

    class Source:
        def _get_entity_id_list(self):
            return ["10", "9", "2"]

        def _build_entity(self, key):
            return Monster(key)

    result = build_status_immunities(Source())
    assert result == {
        "schema_version": 1,
        "npcs": {
            "2": {
                "name": "Fixture",
                "immune_poison": False,
                "immune_venom": True,
                "freeze_resistance": 0,
            },
            "10": {
                "name": "Fixture",
                "immune_poison": False,
                "immune_venom": True,
                "freeze_resistance": 0,
            },
        },
    }


def test_export_carries_the_builders_freeze_resistance():
    from scripts.monsters.status_immunities import build_status_immunities

    class Monster:
        def __init__(self, key):
            self.key = key

        def preprocessing(self):
            return True, ""

        def populate_monster(self):
            builder = parse_builder("freezeresistance=50")
            self.monster_dict = {"id": int(self.key), "name": "Fixture", **builder.monster_dict}
            self.freeze_resistance = builder.freeze_resistance

    class Source:
        def _get_entity_id_list(self):
            return ["7"]

        def _build_entity(self, key):
            return Monster(key)

    assert build_status_immunities(Source())["npcs"]["7"]["freeze_resistance"] == 50


@pytest.mark.parametrize(
    "properties, version, expected",
    [
        ("freezeresistance=50", None, 50),
        ("freezeresistance=33", None, 33),
        ("freezeresistance=100", None, 100),
        ("freezeresistance=100%", None, 100),
        ("freezeresistance=0", None, 0),
        ("freezeresistance=250", None, 100),
        ("freezeresistance=Yes", None, 100),
        ("freezeresistance=Unknown", None, 0),
        ("freezeresistance=", None, 0),
        ("hitpoints=5", None, 0),
        ("freezeresistance=100|freezeresistance2=40", 2, 40),
        ("freezeresistance=100|freezeresistance2=40", 1, 100),
        ("freezeresistance1=60|freezeresistance2=0", 1, 60),
        ("freezeresistance=100", 3, 100),
    ],
)
def test_freeze_resistance_is_a_whole_percentage_with_versioned_values_first(
    properties, version, expected
):
    assert parse_builder(properties, version).freeze_resistance == expected


def test_freeze_resistance_stays_out_of_the_complete_monster_record():
    result = parse_status("freezeresistance=50")
    assert "freeze_resistance" not in result
    assert result["incomplete"] is True  # the fixture lacks other fields; freeze adds nothing


def test_status_export_writes_platform_independent_lf(tmp_path, monkeypatch):
    from scripts.monsters import status_immunities

    monkeypatch.setattr(
        status_immunities,
        "build_status_immunities",
        lambda: {"schema_version": 1, "npcs": {}},
    )
    output = tmp_path / "status.json"
    assert status_immunities.export_status_immunities(output) == 0
    assert output.read_bytes() == b'{\n  "schema_version": 1,\n  "npcs": {}\n}\n'
