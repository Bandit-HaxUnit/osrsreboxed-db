"""Standalone exporter contract tests; runnable without the full data pipeline."""

import csv
import json
import tempfile
import unittest
import math
import runpy
from unittest import mock
from fractions import Fraction
from pathlib import Path

from scripts.drops.reward_caskets import SOURCE, build_beginner, generate, load_item_ids


class RewardCasketTests(unittest.TestCase):
    def test_import_and_generate_without_python39_math_lcm(self):
        with mock.patch.dict(math.__dict__):
            math.__dict__.pop("lcm", None)
            module = runpy.run_path(str(SOURCE.parents[1] / "reward_caskets.py"))
            table = module["build_beginner"](SOURCE, self.ids)
            self.assertEqual(table["out_of"], 44280)

    def setUp(self):
        with SOURCE.open(encoding="utf-8", newline="") as stream:
            self.rows = list(csv.DictReader(stream, delimiter="\t"))
        self.ids = {
            row["name"].casefold(): index + 1 for index, row in enumerate(self.rows)
        }

    def test_complete_exact_probability_distribution(self):
        table = build_beginner(SOURCE, self.ids)
        self.assertEqual(len(table["entries"]), 74)
        self.assertEqual(table["out_of"], 44280)
        self.assertEqual(
            sum(row["weight"] for row in table["entries"]), table["out_of"]
        )
        self.assertEqual(table["rolls"], [1, 3])
        for row in table["entries"]:
            self.assertEqual(
                Fraction(row["weight"], table["out_of"]), Fraction(row["rarity_raw"])
            )

    def test_unique_and_food_semantics(self):
        entries = build_beginner(SOURCE, self.ids)["entries"]
        self.assertEqual(sum(row["unique"] for row in entries), 15)
        self.assertEqual(
            {row["name"] for row in entries if row["noted"]},
            {"Cabbage", "Shrimps", "Sardine", "Herring"},
        )
        cabbage = next(row for row in entries if row["name"] == "Cabbage")
        self.assertEqual(cabbage["quantity"], [5, 9])
        self.assertEqual(cabbage["weight"], 1845)
        pickaxe = next(row for row in entries if row["name"] == "Black pickaxe")
        self.assertFalse(pickaxe["unique"])

    def test_missing_item_fails_closed(self):
        del self.ids["mole slippers"]
        with self.assertRaisesRegex(ValueError, "Unresolved reward item"):
            build_beginner(SOURCE, self.ids)

    def test_truncated_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.tsv"
            source.write_text(
                "\n".join(SOURCE.read_text(encoding="utf-8").splitlines()[:-1]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "sum exactly to one"):
                build_beginner(source, self.ids)

    def test_item_lookup_excludes_notes_and_prefers_wiki_identity(self):
        lookup = load_item_ids(
            {
                "1": {
                    "id": 1, "name": "Wizard hat", "wiki_name": "Blue wizard hat",
                    "tradeable_on_ge": True,
                },
                "2": {
                    "id": 2, "name": "Wizard hat", "wiki_name": "Wizard hat",
                    "tradeable_on_ge": True,
                },
                "3": {
                    "id": 3, "name": "Note", "noted": True,
                    "tradeable_on_ge": True,
                },
            }
        )
        self.assertEqual(lookup["wizard hat"], 2)
        self.assertEqual(lookup["blue wizard hat"], 1)
        self.assertNotIn("note", lookup)

    def test_repeated_generation_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = root / "items.json"
            items.write_text(
                json.dumps(
                    {
                        str(item_id): {
                            "id": item_id, "name": name, "tradeable_on_ge": True
                        }
                        for name, item_id in self.ids.items()
                    }
                ),
                encoding="utf-8",
            )
            first, second = root / "first.json", root / "second.json"
            generate(SOURCE, items, first)
            generate(SOURCE, items, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertNotIn(
                b"\r\n", first.read_bytes(), "exports use canonical LF on Windows too"
            )
            alternate_source = root / "source.tsv"
            alternate_items = root / "items-lf.json"
            alternate_source.write_bytes(
                SOURCE.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            )
            alternate_items.write_bytes(items.read_bytes().replace(b"\r\n", b"\n"))
            third = root / "third.json"
            generate(alternate_source, alternate_items, third)
            self.assertEqual(
                first.read_bytes(),
                third.read_bytes(),
                "checkout line endings do not change provenance",
            )

    def test_unknown_replacement_is_explicit(self):
        table = build_beginner(SOURCE, self.ids)
        self.assertIsNone(table["restrictions"]["ineligible_unique_replacement"])
        self.assertEqual(
            table["restrictions"]["unique_minimum_account_age_seconds"], 36000
        )
        self.assertNotIn(30902, [row["item_id"] for row in table["entries"]])


if __name__ == "__main__":
    unittest.main()
