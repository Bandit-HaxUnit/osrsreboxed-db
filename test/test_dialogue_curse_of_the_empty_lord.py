"""Curse of the Empty Lord's miniquest transcript is exported and indexed to its ghosts."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = "Transcript:Curse of the Empty Lord"
# Wiki NPC IDs of the six ghosts (Rennard, Dhalak, Valdez, Kharrim, Lennissa, Viggora).
GHOSTS = {3450: "rennard", 3451: "dhalak", 3452: "valdez", 3453: "kharrim", 3454: "lennissa", 3455: "viggora"}
# Who each ghost points the player to next, one location per sequence.
NEXT = {
    "valdez": "Rennard",
    "rennard": "Kharrim",
    "kharrim": "Lennissa",
    "lennissa": "Dhalak",
    "dhalak": "Viggora",
}


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf8"))


def conditions(steps):
    found = []
    for step in steps or []:
        if step.get("type") == "condition":
            found.append(step)
        found += conditions(step.get("steps"))
        for option in step.get("options") or []:
            found += conditions(option.get("steps"))
    return found


def test_miniquest_record_is_exported_with_every_ghost_section():
    record = load("docs/npc-dialogues.json")["Curse of the Empty Lord"]
    variants = record["variants"]
    for ghost in GHOSTS.values():
        assert f"talking-to-{ghost}" in variants
        assert f"talking-to-{ghost}-talking-to-{ghost}-again" in variants
    assert "talking-to-any-mysterious-ghost-without-a-ghostspeak-amulet" in variants
    assert "talking-to-any-mysterious-ghost-in-the-wrong-location" in variants


def test_each_ghost_keeps_one_identified_branch_per_sequence():
    variants = load("docs/npc-dialogues.json")["Curse of the Empty Lord"]["variants"]
    for ghost, target in NEXT.items():
        for variant in (f"talking-to-{ghost}", f"talking-to-{ghost}-talking-to-{ghost}-again"):
            located = [c for c in conditions(variants[variant]) if c["text"].startswith(f"If {target} is ")]
            assert len(located) == 3, (variant, located)
            assert all(c.get("id") for c in located)


def test_transcript_is_a_candidate_for_each_ghost():
    index = load("docs/npc-dialogue-index.json")
    for npc_id in GHOSTS:
        assert any(entry["page"] == PAGE for entry in index[str(npc_id)])


def test_cached_source_is_the_reviewed_revision():
    pages = load("data/dialogues/quest-pages.json")
    assert pages[PAGE]["revision"] == 15354024
