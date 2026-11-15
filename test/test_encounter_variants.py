"""Named variants keep Wiki statistics and loot separate from normal NPC IDs."""
import json

import pytest

from scripts.monsters.encounter_variants import (
    MANIFEST, PAGES, build_encounter_variants, profile_from_page, render,
)


@pytest.fixture(scope="module")
def data():
    return build_encounter_variants()


def test_all_nine_encounters_and_roles(data):
    assert len(data["bosses"]) == 9
    kings = data["bosses"]["dagannoth-kings"]["profiles"]
    assert set(kings) == {"rex", "prime", "supreme"}
    assert {row["hitpoints"] for row in kings.values()} == {1800}
    assert kings["rex"]["max_hit"] is None
    assert kings["prime"]["max_hit"] is None
    assert kings["supreme"]["max_hit"] == 26
    assert data["bosses"]["amoxliatl"]["profiles"]["boss"]["source_id"] == "override13685"


def test_versioned_queen_profiles_do_not_overwrite_each_other(data):
    profiles = data["bosses"]["kalphite-queen"]["profiles"]
    assert profiles["ground"]["source_version"] == "1"
    assert profiles["air"]["source_version"] == "2"
    assert profiles["ground"]["hitpoints"] == profiles["air"]["hitpoints"] == 561
    assert profiles["ground"]["defence_magic"] == 65
    assert profiles["air"]["defence_stab"] == 50


def test_current_rewards_and_first_copy_guarantees_are_parsed_from_source(data):
    thermo = data["bosses"]["thermonuclear-smoke-devil"]
    assert {entry["itemId"] for entry in thermo["uniques"]} == {30371, 33253}
    assert all(entry["rate"] == 25 and entry["guarantee"] == 50 for entry in thermo["uniques"])
    queen = data["bosses"]["kalphite-queen"]["uniques"][0]
    assert queen["rate"] == 20 and queen["guarantee"] == 40
    assert len(data["bosses"]["dagannoth-kings"]["normal_sources"]) == 3
    assert all("always" in entry["notes"][0] for entry in thermo["unique_table"]["entries"])


def test_named_export_does_not_touch_regular_id_keyed_monster_output(data):
    assert not any(key.isdigit() for key in data["bosses"])
    amox = data["bosses"]["amoxliatl"]["profiles"]["boss"]
    assert amox["hitpoints"] == 650 and amox["magic_level"] == 240
    assert amox["freeze_resistance"] == 100
    assert "id" not in amox


def test_repeat_generation_is_byte_identical(data):
    assert render(data) == render(build_encounter_variants())


def test_blank_wiki_values_stay_unresolved_instead_of_zero_or_empty(data):
    # Hespori (Echo) leaves |size blank and King Black Dragon (Echo) |id: neither is invented.
    assert data["bosses"]["hespori"]["profiles"]["boss"]["size"] is None
    assert data["bosses"]["king-black-dragon"]["profiles"]["boss"]["source_id"] is None
    pages = json.loads(PAGES.read_text(encoding="utf-8"))
    blank = pages["Hespori (Echo)"]
    assert "|size = \n" in blank, "the regression needs the page's blank size field"
    filled = blank.replace("|size = \n", "|size = 3\n", 1)
    assert profile_from_page("Hespori (Echo)", filled)["size"] == 3, "a given size still parses"


def test_live_source_changes_reach_the_export_without_stat_overrides():
    pages = json.loads(PAGES.read_text(encoding="utf-8"))
    changed = pages["Cerberus (Echo)"].replace("|hitpoints = 1620", "|hitpoints = 1621")
    assert profile_from_page("Cerberus (Echo)", changed)["hitpoints"] == 1621


def test_normal_inheritance_stays_as_references_not_duplicate_reward_tables(data):
    expected = {
        "amoxliatl": ["Amoxliatl#Drops"],
        "cerberus": ["Cerberus#Drops"],
        "corrupted-hunllef": ["Reward Chest (The Gauntlet)#Corrupted Gauntlet Completed"],
        "dagannoth-kings": ["Dagannoth Prime#Drops", "Dagannoth Rex#Drops", "Dagannoth Supreme#Drops"],
        "grotesque-guardians": ["Grotesque Guardians#Drops"],
        "hespori": ["Hespori#Drops"],
        "kalphite-queen": ["Kalphite Queen#Drops"],
        "king-black-dragon": ["King Black Dragon#Drops"],
        "thermonuclear-smoke-devil": ["Thermonuclear smoke devil#Drops"],
    }
    for boss, sources in expected.items():
        row = data["bosses"][boss]
        assert row["normal_sources"] == sources
        assert len(row["unique_table"]["entries"]) == len(row["uniques"])
        assert {entry["item_id"] for entry in row["unique_table"]["entries"]} == {
            entry["itemId"] for entry in row["uniques"]
        }
        assert all(entry["guarantee"] == 2 * entry["rate"] for entry in row["uniques"])


def test_missing_or_changed_guarantee_is_rejected_instead_of_invented():
    from scripts.monsters.encounter_variants import unique_drops
    from scripts.drops import drops_tables
    from osrsreboxed import items_api

    pages = json.loads(PAGES.read_text(encoding="utf-8"))
    page = "Cerberus (Echo)"
    text = pages[page]
    changed = text.replace("50th", "51st")
    assert changed != text
    with pytest.raises(ValueError, match="Missing or inconsistent first-copy guarantee"):
        unique_drops(page, changed, drops_tables.ItemIdLookup(items_api.load()))
