"""Recorded interface titles must not change shop identity or owner bindings."""

import json

import pytest

import config
from scripts.shops import shop_owners, shops_items


@pytest.fixture
def shop_export(tmp_path, monkeypatch):
    data = tmp_path / "data"
    docs = tmp_path / "docs"
    package = tmp_path / "package"
    data.mkdir()
    docs.mkdir()
    raw = {
        name: {"shop_info": {"currency": "coins"}, "items": []}
        for name in ("Auburn Pub", "The Pandemonium (pub)", "The Flaming Arrow")
    }
    (data / "shops-raw.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_SHOPS_PATH", data)
    monkeypatch.setattr(config, "DOCS_PATH", docs)
    monkeypatch.setattr(config, "PACKAGE_PATH", package)
    monkeypatch.setattr(shop_owners, "load", lambda: {})
    monkeypatch.setattr(shop_owners, "load_npc_options", lambda: {})
    return data, docs, package


def recorded_title(title="The Auburn Pub"):
    return {
        "display_name": title,
        "sources": [
            {"recording": "232/03127", "line": 13254, "inventory": "pub_auburnvale"}
        ],
    }


def test_process_preserves_source_keys_and_repeats_identically(shop_export):
    data, docs, package = shop_export
    titles = {
        "Auburn Pub": recorded_title(),
        "The Pandemonium (pub)": recorded_title("The Pandemonium"),
    }
    (data / "shop-display-names.json").write_text(json.dumps(titles), encoding="utf-8")
    shops_items.process()
    first = (docs / "shops-items-by-shop.json").read_bytes()
    npc_first = (docs / "shops-by-npc.json").read_bytes()
    result = json.loads(first)
    assert set(result) == {"Auburn Pub", "The Pandemonium (pub)", "The Flaming Arrow"}
    assert result["Auburn Pub"]["display_name"] == "The Auburn Pub"
    assert result["The Pandemonium (pub)"]["display_name"] == "The Pandemonium"
    assert "display_name" not in result["The Flaming Arrow"]
    assert (package / "docs" / "shops-items-by-shop.json").read_bytes() == first
    shops_items.process()
    assert (docs / "shops-items-by-shop.json").read_bytes() == first
    assert (docs / "shops-by-npc.json").read_bytes() == npc_first


@pytest.mark.parametrize(
    "titles",
    [
        {"Unknown pub": recorded_title()},
        {
            "Auburn Pub": recorded_title(),
            "The Auburn Pub": recorded_title("Another Pub"),
        },
        {"Auburn Pub": recorded_title("")},
        {"Auburn Pub": recorded_title("The Flaming Arrow")},
        {"Auburn Pub": {"display_name": "The Auburn Pub", "sources": []}},
        {
            "Auburn Pub": {
                "display_name": "The Auburn Pub",
                "sources": [{"recording": "bad"}],
            }
        },
    ],
)
def test_invalid_recorded_title_fails_before_writing(shop_export, titles):
    data, docs, _ = shop_export
    (data / "shop-display-names.json").write_text(json.dumps(titles), encoding="utf-8")
    with pytest.raises(ValueError):
        shops_items.process()
    assert not (docs / "shops-items-by-shop.json").exists()


def test_canonical_recordings_cover_only_the_two_confirmed_mismatches():
    titles = json.loads(
        (config.DATA_SHOPS_PATH / "shop-display-names.json").read_text(encoding="utf-8")
    )
    assert {key: entry["display_name"] for key, entry in titles.items()} == {
        "Auburn Pub": "The Auburn Pub",
        "The Pandemonium (pub)": "The Pandemonium",
    }
