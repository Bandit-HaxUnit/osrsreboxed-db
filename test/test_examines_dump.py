"""
Description:
Tests for module: scripts/examines

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

from scripts.examines.examines_wikitext import examines_of, infoboxes, plain_text

TREE_PAGE = """{{Infobox Scenery
|version1 = Double canopy
|version2 = Single canopy
|name = Tree
|examine1 = One of the most common trees in [[Gielinor]].
|examine2 = A commonly found tree.
|id1 = 1276
|id2 = 1278, 1279
}}
'''Trees''' are found all over Gielinor."""


def test_each_version_pairs_its_ids_with_its_examine():
    assert examines_of(infoboxes(TREE_PAGE)[0]) == [
        (1276, "One of the most common trees in Gielinor."),
        (1278, "A commonly found tree."),
        (1279, "A commonly found tree."),
    ]


def test_an_unversioned_infobox_uses_its_plain_id_and_examine():
    box = infoboxes("{{Infobox Scenery|name=Rusted anvil|examine=An old anvil.|id=39620}}")[0]
    assert examines_of(box) == [(39620, "An old anvil.")]


def test_infoboxes_inside_other_templates_are_read():
    page = "{{Switch infobox|item1={{Infobox Scenery|examine=A cosy fire.|id=4650}}}}"
    assert [examines_of(box) for box in infoboxes(page)] == [[(4650, "A cosy fire.")]]


def test_markup_is_stripped_and_na_means_no_examine():
    assert plain_text("It's a [[Sailing|boat]]<ref>Seen in 2025.</ref>, ''really''.") == "It's a boat, really."
    assert examines_of({"examine": "N/A", "id": "1"}) == []


def test_one_examine_of_several_listed_per_line():
    assert plain_text("* Lets you put items into your bank.\n* It banks your bits.") == "Lets you put items into your bank."
    labelled = "'''Throne Room:''' You can build various fiendish devices here.<br/>\n'''Oubliette:''' You can build various things here."
    assert plain_text(labelled) == "You can build various fiendish devices here."


def test_a_two_state_text_gives_the_lit_state():
    box = {"examine": "(Unlit) You can light a fire here.<br>(Lit) A fire burns steadily in the grate.", "id": "4618"}
    assert examines_of(box) == [(4618, "A fire burns steadily in the grate.")]
