import json
import unittest

from scripts.items.item_spawns import build_export, parse_pages


def page(extra="", item_id="554", respawn="100"):
    return (
        "{{Infobox Item|name=Fire rune|id="
        + item_id
        + "|respawn="
        + respawn
        + "}}"
        + extra
    )


class ItemSpawnExportTests(unittest.TestCase):
    def test_quantity_plane_members_and_separate_timer_sources(self):
        rows = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|location=Fortress|members=No|plane=1"
                    "|3026,3637,qty:5|3021,3640,qty:5,respawn:50}}"
                )
            }
        )
        self.assertEqual(
            (rows[0]["id"], rows[0]["quantity"], rows[0]["plane"], rows[0]["members"]),
            (554, 5, 1, False),
        )
        self.assertEqual(rows[0]["infobox_respawn_ticks"], 100)
        self.assertEqual(rows[0]["unresolved_reasons"], [])
        self.assertEqual(rows[1]["tile_respawn_raw"], "50")
        self.assertIn("untyped-tile-respawn", rows[1]["unresolved_reasons"])

    def test_defaults_and_zero_id_are_preserved(self):
        row = parse_pages(
            {"Fire rune": page("{{ItemSpawnLine|name=Fire rune|1,2}}", item_id="0")}
        )[0]
        self.assertEqual(
            (row["id"], row["quantity"], row["plane"], row["members"]), (0, 1, 0, False)
        )

    def test_no_guessed_duration_or_variable_quantity(self):
        row = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|1,2,qty:1-5}}", respawn=""
                )
            }
        )[0]
        self.assertIsNone(row["quantity"])
        self.assertIsNone(row["infobox_respawn_ticks"])
        self.assertIn("unresolved-quantity", row["unresolved_reasons"])
        self.assertIn("missing-positive-infobox-respawn", row["unresolved_reasons"])

    def test_version_ambiguity_notes_and_malformed_arguments_survive(self):
        text = (
            "{{Infobox Item|name=Fire rune|id1=1|id2=2|respawn=100}}"
            "{{ItemSpawnLine|name=Fire rune|group=historical|1,2,notes:after quest|not a tile}}"
        )
        rows = parse_pages({"Fire rune": text})
        self.assertEqual(len(rows), 2)
        self.assertIn("ambiguous-item-id", rows[0]["unresolved_reasons"])
        self.assertIn(
            "coordinate-condition-or-unknown-qualifier", rows[0]["unresolved_reasons"]
        )
        self.assertIn(
            "row-selection-or-unknown-parameter", rows[0]["unresolved_reasons"]
        )
        self.assertIn("unparsed-coordinate", rows[1]["unresolved_reasons"])
        self.assertEqual(rows[0]["coordinate_qualifiers"]["notes"], "after quest")

    def test_nested_templates_and_links_do_not_split_coordinates(self):
        rows = parse_pages(
            {
                "Fire rune": page(
                    "{{ItemSpawnLine|name=Fire rune|location=[[Al Kharid mine|mine]] {{Refn|a|b}}|3304,3311,qty:3}}"
                )
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["x"], rows[0]["quantity"]), (3304, 3))

    def test_named_item_version_selects_its_id_and_typed_default(self):
        text = (
            "{{Infobox Item|name1=Potion(4)|id1=2428|respawn1=100"
            "|name2=Potion(1)|id2=125|respawn2=200}}"
            "{{ItemSpawnLine|name=Potion(1)|1,2}}"
        )
        row = parse_pages({"Potion": text})[0]
        self.assertEqual((row["id"], row["infobox_respawn_ticks"]), (125, 200))
        self.assertEqual(row["unresolved_reasons"], [])

    def test_deterministic_export_and_exact_raw_page_identity(self):
        raw = json.dumps(
            {"Fire rune": page("{{ItemSpawnLine|name=Fire rune|1,2}}")}
        ).encode()
        self.assertEqual(build_export(raw), build_export(raw))
        self.assertEqual(len(build_export(raw)["rows"][0]["page_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
