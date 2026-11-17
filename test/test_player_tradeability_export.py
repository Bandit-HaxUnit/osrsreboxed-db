import json
from pathlib import Path

from scripts.items.export_player_tradeability import build_export, export_bytes, export_source_bytes


def test_exact_version_ids_use_explicit_yes_no_not_exchange_or_missing_defaults():
    pages = {
        "Mask": "{{Infobox Item|name1=Mask (1)|id1=11|name2=Mask (2)|id2=12|tradeable=Yes|exchange=No}}",
        "Pack": "{{Infobox Item|name=Pack|id=20|tradeable=No|noteable=Yes}}",
        "Unknown": "{{Infobox Item|id=30|exchange=No}}",
        "Mixed": "{{Infobox Item|name=Mixed|id1=40|id3=42|tradeable=Yes|tradeable3=No}}",
    }
    result = build_export(pages, "a" * 64)
    assert [(r["id"], r["playerTradeable"]) for r in result["rows"]] == [
        (11, True),
        (12, True),
        (20, False),
        (40, True),
        (42, False),
    ]
    assert result["rows"][1]["sourceVersion"] == 2
    assert result["rows"][2]["sourceVersion"] is None
    assert result["rows"][2]["noteable"] is True
    assert result["rows"][0]["noteable"] is None
    assert any(d["reason"] == "unknown-tradeability" for d in result["diagnostics"])


def test_conflicting_ids_are_omitted_and_malformed_fields_are_not_inferred():
    pages = {
        "A": "{{Infobox Item|name=Same|id=1|tradeable=Yes}}",
        "B": "{{Infobox Item|name=Same|id=1|tradeable=No}}",
        "C": "{{Infobox Item|name=Other|id=2|tradeable=Sometimes}}",
        "D": "{{Infobox Item|name=Other|id=3 or 4|tradeable=No}}",
        "E": "{{Infobox Item|name=Other|id=5|tradeable=Yes|tradeable=No}}",
    }
    result = build_export(pages, "b" * 64)
    assert result["rows"] == []
    assert {d["reason"] for d in result["diagnostics"]} >= {
        "conflicting-id",
        "unknown-tradeability",
        "malformed-id",
        "duplicate-field",
    }


def test_deterministic_bytes_include_all_exact_ids_and_provenance():
    pages = {"Pack": "{{Infobox Item|name=Pack|id=4, 5|tradeable=No}}"}
    a = export_bytes(pages, "c" * 64)
    b = export_bytes(dict(reversed(list(pages.items()))), "c" * 64)
    assert a == b
    data = json.loads(a)
    assert [r["id"] for r in data["rows"]] == [4, 5]
    assert data["rows"][1]["sourcePage"] == "Pack"
    assert data["input_sha256"] == "c" * 64


def test_checkout_line_endings_do_not_change_source_digest_or_output():
    source = b'{\n"Pack": "{{Infobox Item|name=Pack|id=4|tradeable=No}}"\n}\n'
    assert export_source_bytes(source) == export_source_bytes(source.replace(b"\n", b"\r\n"))


def test_case_only_page_aliases_are_consistent_but_policy_conflicts_remain_unknown():
    pages = {
        "A": "{{Infobox Item|name=Third Age|id=1|tradeable=Yes}}",
        "B": "{{Infobox Item|name=Third age|id=1|tradeable=Yes}}",
    }
    result = build_export(pages, "d" * 64)
    assert result["rows"][0]["playerTradeable"] is True
    assert result["diagnostics"][0]["reason"] == "duplicate-consistent-id"


def test_exact_cached_policy_boundaries_and_noteability_have_matching_item_ids():
    pages = json.loads(
        (
            Path(__file__).resolve().parents[1] / "data/items/items-wiki-page-text.json"
        ).read_text(encoding="utf-8")
    )
    selected = {
        name: pages[name]
        for name in [
            "Black mask",
            "Ring of dueling",
            "Burnt meat",
            "Shark lure pack",
            "Moonlight antler",
            "Archaic emblem",
            "Archaic emblem (discontinued)",
        ]
    }
    rows = {row["id"]: row for row in build_export(selected, "e" * 64)["rows"]}
    for item_id in [8903, 8919, 2554, 2566, 2146, 12746]:
        assert rows[item_id]["playerTradeable"] is True
    for item_id in [34065, 28887, 12747]:
        assert rows[item_id]["playerTradeable"] is False
    assert rows[34065]["noteable"] is True
    assert rows[28887]["noteable"] is True
    assert rows[12747]["noteable"] is False
