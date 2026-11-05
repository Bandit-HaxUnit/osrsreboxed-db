"""Captured supplemental monster pages keep their raw source receipt."""

import hashlib
import json
from pathlib import Path

import config
from scripts.monsters import supplemental_pages


def test_supplemental_manifest_matches_the_captured_wikitext():
    manifest = supplemental_pages.load_pages()
    assert "Demonic larva" in manifest

    with open(Path(config.DATA_MONSTERS_PATH / "monsters-wiki-page-text.json")) as f:
        wikitext = json.load(f)

    for title, entry in manifest.items():
        text = wikitext[title]
        assert hashlib.sha256(text.encode()).hexdigest() == entry["sha256"]
        assert entry["revision"] > 0
        assert entry["categories"]
        assert "{{Infobox NPC" in text
