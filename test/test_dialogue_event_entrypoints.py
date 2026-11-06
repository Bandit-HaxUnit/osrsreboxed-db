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


def test_holiday_item_transcripts_export_as_item_option_conversations():
    root = Path(__file__).resolve().parents[1]
    aggregate = json.loads(
        (root / "docs/npc-dialogues.json").read_text(encoding="utf8")
    )
    types = json.loads((root / "docs/dialogue-types.json").read_text(encoding="utf8"))
    index = json.loads(
        (root / "docs/npc-dialogue-index.json").read_text(encoding="utf8")
    )
    for name in ("Haunted wine bottle", "Magic egg ball", "Secret santa present"):
        # Played by the item's option, never chosen for an NPC's Talk-to.
        assert aggregate[name]["activation"] == "explicit"
        assert "Transcript:" + name in types["item"]
    bottle = aggregate["Haunted wine bottle"]["variants"]
    assert [step for step in bottle["talking-to-the-bottle-without-a-ghostspeak-amulet"]
            if "player" in step] == [{"player": "Hello...?"}]
    egg = aggregate["Magic egg ball"]
    pets = next(option for option in egg["steps"][0]["options"]
                if option["text"] == "Will I get a pet today?")
    # The pet question's {{tact|above}} shares the rare-item question's answers.
    call = pets["steps"][-1]["steps"][0]
    assert call["type"] == "call" and call["branch"] in egg["branches"]
    santa = aggregate["Secret santa present"]["variants"]
    assert santa["unlocking-blue-read-tag"][0]["text"].startswith("I sell tools that chop.")
    # Deliveries stay indexed to their NPCs as explicit candidates (Bob, Aggie...).
    assert any(
        entry["page"] == "Transcript:Secret santa present"
        and entry["variants"] == ["unlocking-blue-talking-to-bob"]
        for entries in index.values()
        for entry in entries
    )
