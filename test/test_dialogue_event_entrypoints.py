"""An event source must remain opt-in after parsing and runtime compaction."""

import json
from pathlib import Path

import jsonschema

from scripts.dialogues import update
from scripts.dialogues.compact import compact_record
from scripts.dialogues.hooks import enrich_records, walk


def record(name, raw):
    result = update.gameplay_npc(name, update.parse_npc(name, raw))
    result["source"] = {"page": "Transcript:" + name, "revision": 1}
    return result


def test_event_stays_explicit_through_parse_identity_enrichment_and_compaction():
    event = record(
        "Christmas event",
        """{{Transcript|event}}
{{Transcript list|Cook (Blue Moon Inn)}}
==Starting off==
* '''Cook:''' Help!
* {{tselect|Start the Christmas event?}}
* {{topt|Yes.}}
** '''Player:''' I can help.
* {{topt|No.}}
** {{tact|end}}
""",
    )
    npc = record("Cook (Blue Moon Inn)", "* '''Cook:''' The usual menu.")
    identity = {
        "Cook (Blue Moon Inn)": {"wikitext": "{{Infobox NPC|name=Cook|id=2895}}"}
    }
    index = enrich_records(
        {"Cook (Blue Moon Inn)": npc},
        {"Christmas event": event},
        identity,
        update.clean,
    )
    assert event.get("activation") == "explicit"
    assert all(
        "hook" not in node
        for steps in event["variants"].values()
        for node in walk(steps)
    )
    assert any(entry["page"] == "Transcript:Christmas event" for entry in index["2895"])
    compact_record(event)
    assert event["activation"] == "explicit"
    schema = json.loads(
        Path("data/schemas/schema-dialogues.json").read_text(encoding="utf8")
    )
    jsonschema.validate({"Christmas event": event}, schema)


def test_a_quest_retains_its_start_hook_and_implicit_activation():
    quest = record(
        "A quest",
        """{{Transcript|quest}}
==Starting off==
* {{tselect|Start the A quest quest?}}
* {{topt|Yes.}}
** '''Player:''' I can help.
""",
    )
    enrich_records({}, {"A quest": quest}, {}, update.clean)
    assert "activation" not in quest
    assert any(
        node.get("hook") == "quest:a-quest:start"
        for steps in quest["variants"].values()
        for node in walk(steps)
    )


def test_commented_or_nested_event_words_do_not_reclassify_a_npc():
    npc = record(
        "Cook",
        """<!-- {{Transcript|event}} -->
{{Transcript|npc}}
* '''Cook:''' I mentioned an event.
""",
    )
    assert "activation" not in npc


def test_exported_event_catalogue_is_the_exact_opt_in_subset():
    root = Path(__file__).resolve().parents[1]
    catalogue = json.loads(
        (root / "docs/event-dialogues.json").read_text(encoding="utf8")
    )
    aggregate = json.loads(
        (root / "docs/npc-dialogues.json").read_text(encoding="utf8")
    )
    assert catalogue == {
        name: value
        for name, value in aggregate.items()
        if value.get("activation") == "explicit"
    }
    assert {
        "2025 Christmas event",
        "2025 Easter event",
        "2026 Easter event",
        "2025 Halloween event",
        "25th Anniversary event",
    } <= catalogue.keys()
    schema = json.loads(
        (root / "data/schemas/schema-dialogues.json").read_text(encoding="utf8")
    )
    jsonschema.validate(catalogue, schema)
    assert "activation" not in aggregate["Cook (Blue Moon Inn)"]
    from osrsreboxed.dialogues import DialogueRecord, FlatDialogueRecord

    for record in catalogue.values():
        model = FlatDialogueRecord if "steps" in record else DialogueRecord
        assert model(**record).activation == "explicit"


def test_halloween_2025_above_jumps_and_lost_picture_play_their_source_branches():
    """The 2025 Halloween transcript's "above" jumps point back at whole branches on
    other sections (navigation anchors in runtime-bindings.json), and Seth's
    replacement picture is not nested under the all-decorations message
    (corrections.json). A consumer must be able to play the export as published."""
    root = Path(__file__).resolve().parents[1]
    event = json.loads((root / "docs/event-dialogues.json").read_text(encoding="utf8"))[
        "2025 Halloween event"
    ]

    def find(steps, wanted):
        for node in walk(steps):
            if node.get("id") == wanted:
                return node
        return None

    def ids(steps):
        return [node.get("id") for node in walk(steps) if node.get("id")]

    def jump_body(variant, jump_id):
        jump = find(event["variants"][variant], jump_id)
        assert jump is not None and jump["type"] == "jump"
        assert [step["type"] for step in jump["steps"]] == ["call"]
        return event["branches"][jump["steps"][0]["branch"]]

    # Diango's second visit continues as his first: the wearing check hands out the lantern.
    diango = jump_body("spooky-pumpkin-lantern-talking-to-diango-again", "Kg0hmG")
    assert [step.get("id") for step in diango] == ["9NWeHn", "_MxZad"]
    assert "BSrsl1" in ids(diango)
    # Fred's "I'm ready for the judgement!" continues into the judging and its rewards.
    fred = jump_body(
        "the-spook-a-thon-contest-talking-to-fred-again-before-finishing-the-cutscene",
        "kzB_xv",
    )
    assert [step.get("id") for step in fred] == ["4Sjcyo", "H4FTU9"]
    assert "5shIok" in ids(fred)

    lost = find(
        event["variants"][
            "starting-off-talking-to-seth-again-after-receiving-the-picture-for-the-first-time"
        ],
        "1Glkal",
    )
    tail = [step.get("id") for step in lost["steps"][2:]]
    assert tail == ["UBDVQJ", "pMyO2X", "Nkt5y6"]
    assert lost["steps"][2]["steps"][-1] == {"type": "end"}
    assert ids(lost["steps"][3]["steps"]) == ["tdDfyd"]
    assert not any(
        node.get("type") == "jump" and not node.get("steps")
        for node in walk(lost["steps"])
    )
