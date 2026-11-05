"""Monster infobox cleaning for current Wiki ranged/plainlist/attack values."""

from builders.monsters import infobox_cleaner


def test_scaling_stat_range_uses_the_base_value():
    assert infobox_cleaner.stats("210-<br />280{{efn|name=def}}") == 210
    assert infobox_cleaner.stats("180-<br />130{{efn|name=def}}") == 180


def test_max_hit_leading_range_uses_its_maximum():
    assert infobox_cleaner.max_hit("30-37 ([[Melee]]){{efn|name=def}}, ?? (axes)") == 37


def test_max_hit_decreasing_range_is_not_a_maximum():
    assert infobox_cleaner.max_hit("6-5,(11 total)") is None


def test_max_hit_plainlist_prefers_the_auto_attack():
    # The singular export field describes the auto attack; the special value is
    # not promoted, even when it is listed first.
    assert infobox_cleaner.max_hit("{{plainlist|\n*31 (auto)\n*45 (special)}}") == 31
    assert infobox_cleaner.max_hit("{{plainlist|\n*45 (special)\n*31 (auto)}}") == 31


def test_max_hit_plainlist_mixed_styles_uses_the_highest():
    # Without an auto label the field is the monster's maximum across styles.
    assert (
        infobox_cleaner.max_hit("{{plainlist|\n*Melee: 20\n*Ranged: 30\n*Magic: 25}}")
        == 30
    )


def test_attack_type_all_expands_to_every_style():
    assert infobox_cleaner.attack_type("All") == ["melee", "ranged", "magic"]


def test_categories_supply_npc_infobox_attributes():
    assert infobox_cleaner.categories_to_attributes(
        ["Category:Demons", "Category:Doom of Mokhaiotl"]
    ) == ["demon"]
