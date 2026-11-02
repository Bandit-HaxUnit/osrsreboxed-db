"""
Description:
Tests for modules: scripts/weapons and scripts/sequences

###############################################################################
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
###############################################################################
"""

import json

from scripts.sequences.update import sequence_names
from scripts.sequences.update import write_dump as write_names
from scripts.weapons.update import weapon_dump, write_dump


def stat_row(page, sub=None, slot="weapon", **columns):
    row = {"page_name": page, "page_name_sub": sub or page, "equipment_slot": slot}
    row.update(columns)
    return row


def item_row(page, sub=None, *ids):
    return {
        "page_name": page,
        "page_name_sub": sub or page,
        "item_id": [str(i) for i in ids],
    }


WHIP = stat_row(
    "Abyssal whip",
    combat_style="Whip",
    weapon_attack_speed=4,
    weapon_attack_range="1",
    slash_attack_bonus=82,
    strength_bonus=82,
)


def test_a_weapon_row_is_keyed_by_its_item_ids_with_items_json_names():
    dump = weapon_dump(
        {"bonuses": [WHIP], "items": [item_row("Abyssal whip", None, 4151)]}
    )
    assert dump == {
        4151: {
            "page": "Abyssal whip",
            "slot": "weapon",
            "combat_style": "Whip",
            "attack_speed": 4,
            "attack_range": 1,
            "bonuses": {"attack_slash": 82, "melee_strength": 82},
        }
    }


def test_an_item_takes_the_stat_row_of_its_own_page_version():
    bonuses = [
        stat_row("Crystal bow", "Crystal bow#Active", "2h", range_attack_bonus=100),
        stat_row("Crystal bow", "Crystal bow#Inactive", "2h", range_attack_bonus=0),
    ]
    items = [
        item_row("Crystal bow", "Crystal bow#Active", 23983),
        item_row("Crystal bow", "Crystal bow#Inactive", 23985),
    ]
    dump = weapon_dump({"bonuses": bonuses, "items": items})
    assert dump[23983]["bonuses"] == {"attack_ranged": 100}
    assert dump[23985]["bonuses"] == {"attack_ranged": 0}


def test_an_unmatched_version_falls_back_only_to_a_pages_single_row():
    single = weapon_dump(
        {
            "bonuses": [WHIP],
            "items": [item_row("Abyssal whip", "Abyssal whip#Tradeable", 4151)],
        }
    )
    assert single[4151]["page"] == "Abyssal whip"

    two_rows = [
        stat_row("Crystal bow", "Crystal bow#Active", "2h"),
        stat_row("Crystal bow", "Crystal bow#Inactive", "2h"),
    ]
    ambiguous = weapon_dump(
        {
            "bonuses": two_rows,
            "items": [item_row("Crystal bow", "Crystal bow#New", 4212)],
        }
    )
    assert ambiguous == {}


def test_an_item_id_listed_twice_keeps_the_first_page():
    bonuses = [WHIP, stat_row("Volcanic abyssal whip", slash_attack_bonus=90)]
    items = [
        item_row("Abyssal whip", None, 4151),
        item_row("Volcanic abyssal whip", None, 4151, 12773),
    ]
    dump = weapon_dump({"bonuses": bonuses, "items": items})
    assert dump[4151]["page"] == "Abyssal whip"
    assert dump[12773]["page"] == "Volcanic abyssal whip"


def test_only_weapon_and_two_handed_rows_are_dumped():
    bonuses = [WHIP, stat_row("Helm of Neitiznot", slot="head", prayer_bonus=3)]
    items = [
        item_row("Abyssal whip", None, 4151),
        item_row("Helm of Neitiznot", None, 10828),
    ]
    assert list(weapon_dump({"bonuses": bonuses, "items": items})) == [4151]


def test_the_dump_is_one_item_per_line_and_valid_json(tmp_path):
    out = tmp_path / "weapon-stats.json"
    dump = weapon_dump(
        {
            "bonuses": [WHIP, stat_row("Bronze dagger", stab_attack_bonus=4)],
            "items": [
                item_row("Abyssal whip", None, 4151),
                item_row("Bronze dagger", None, 1205),
            ],
        }
    )
    write_dump(dump, out)
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[1].startswith('"1205":')
    assert len(text.splitlines()) == 4
    assert list(json.loads(text)) == ["1205", "4151"]


def test_sequence_names_keep_the_first_name_of_an_id(tmp_path):
    source = """
    public final class AnimationID
    {
        public static final int HUMAN_SWORD_SLASH = 390;
        public static final int HUMAN_SWORD_STAB = 386;
        public static final int HUMAN_SWORD_SLASH_DUPLICATE = 390;
    }
    """
    names = sequence_names(source)
    assert names == {386: "HUMAN_SWORD_STAB", 390: "HUMAN_SWORD_SLASH"}

    out = tmp_path / "sequence-names.json"
    write_names(names, out)
    assert json.loads(out.read_text(encoding="utf-8")) == {
        "386": "HUMAN_SWORD_STAB",
        "390": "HUMAN_SWORD_SLASH",
    }
