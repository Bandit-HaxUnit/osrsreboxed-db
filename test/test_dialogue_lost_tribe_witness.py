"""The Lost Tribe's cellar witness is any one of four Lumbridge NPCs, named by a placeholder.

Wiki revision 15398483 replaced the fixed Bob witness with "the NPC who saw the goblin" ("can be
the cook, hans, bob, or aereck"): the witness's lines are spoken by ``NPC`` and the player names
them as ``[NPC]``, for the consumer to fill in. Bob, Father Aereck and Donie/Gee answer like the
Cook and Hans when they are not the witness. RSProx capture 20261112T152024-5ab63b4 (revision 242)
plays the witness lines for Hans, ticks 69-73, and the Duke's option as "Hans says he saw something
in the cellar", tick 115.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = "Transcript:The Lost Tribe"
WITNESS = "a-hole-in-the-wall-talking-to-the-npc-who-saw-the-goblin"


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf8"))


def variants():
    return load("docs/npc-dialogues.json")["The Lost Tribe"]["variants"]


def lines(steps):
    found = []
    for step in steps or []:
        if isinstance(step.get("text"), str) or isinstance(step.get("player"), str):
            found.append(step)
        found += lines(step.get("steps"))
        for option in step.get("options") or []:
            found += lines(option.get("steps"))
    return found


def test_cached_source_is_the_reviewed_revision():
    assert load("data/dialogues/quest-pages.json")[PAGE]["revision"] == 15398483


def test_witness_lines_are_spoken_by_the_placeholder_npc():
    spoken = [step for step in lines(variants()[WITNESS]) if step.get("type") == "line"]
    assert [step["speaker"] for step in spoken] == ["NPC"] * 4
    assert spoken[-1]["text"].startswith("Thank you, [player name]! If you can convince the Duke")
    again = lines(variants()[f"{WITNESS}-talking-to-them-again"])
    assert any(step.get("speaker") == "NPC" and step["text"].startswith("I told you about the creature") for step in again)


def test_the_player_names_the_witness_by_placeholder():
    duke = lines(variants()["a-hole-in-the-wall-convincing-horacio"])
    assert any(step.get("player") == "[NPC] says he saw something in the cellar. Like a goblin with big eyes." for step in duke)
    brooch = lines(variants()["a-hole-in-the-wall-showing-the-brooch-to-the-duke"])
    assert any("enough to prove [NPC]'s story" in step.get("text", "") for step in brooch)
    assert not any("Bob" in (step.get("text") or step.get("player") or "") for step in duke + brooch)


def test_every_candidate_has_its_non_witness_answer():
    record = variants()
    assert "a-hole-in-the-wall-asking-the-cook" in record
    assert "a-hole-in-the-wall-asking-hans" in record
    bob = lines(record["a-hole-in-the-wall-asking-bob"])
    assert any(step.get("speaker") == "Bob" and step["text"].startswith("No. But we should find") for step in bob)
    aereck = lines(record["a-hole-in-the-wall-asking-father-aereck"])
    assert any(step.get("speaker") == "Father Aereck" and step["text"].startswith("It's a shame, isn't it?") for step in aereck)
    assert "a-hole-in-the-wall-asking-donie-or-gee" in record


def test_father_aereck_is_a_candidate():
    index = load("docs/npc-dialogue-index.json")
    assert any(entry["page"] == PAGE for entry in index["2812"])
