import pytest

from scripts.dialogues import update
from scripts.dialogues.hooks import enrich_records, walk
from scripts.dialogues.bindings import apply_bindings


def record(name, raw):
    value = update.gameplay_npc(name, update.parse_npc(name, raw))
    value["source"] = {"page": "Transcript:" + name, "revision": 1}
    return value


def follow(record, steps, visiting=frozenset()):
    result = []
    for node in steps:
        if node.get("type") == "call" and node["branch"] not in visiting:
            result.extend(
                follow(
                    record,
                    record["branches"][node["branch"]],
                    visiting | {node["branch"]},
                )
            )
        elif node.get("type") == "jump" and node.get("steps"):
            result.extend(follow(record, node["steps"], visiting))
        else:
            result.append(node)
    return result


def test_nested_menu_does_not_swallow_outer_options_or_drop_same_depth_speech():
    value = record(
        "X",
        """==Standard dialogue==
* {{tselect}}
* {{topt|Outer}}
** {{tselect}}
*** {{topt|Inner}}
*** '''X:''' Inner reply.
*** {{topt|Another inner}}
**** {{tact|end}}
* {{topt|Another outer}}
** '''X:''' Outer reply.
""",
    )
    menu = value["variants"]["standard-dialogue"][0]
    assert [option["text"] for option in menu["options"]] == ["Outer", "Another outer"]
    inner = menu["options"][0]["steps"][0]
    assert [option["text"] for option in inner["options"]] == ["Inner", "Another inner"]
    assert inner["options"][0]["steps"] == [{"npc": "Inner reply."}]


def test_poem_warning_and_editorial_notes_preserve_game_text():
    value = record(
        "X",
        """==Report==
<poem>
Designation: Ally
Race: Siren
</poem>
* Before starting this quest, be aware that your combat level is too low.
* '''Player:''' I know!{{^|This is an editorial note.}}
""",
    )
    steps = value["variants"]["report"]
    assert steps[0] == {"type": "message", "text": "Designation: Ally\nRace: Siren"}
    assert steps[1]["type"] == "message"
    assert steps[2] == {"player": "I know!"}
    with pytest.raises(ValueError, match="Unclosed poem"):
        record("X", "==Report==\n<poem>\nDon't drop me.")

    value = record(
        "X",
        "==Report==\n* {{tcond|If ready:}}\n** '''X:''' Outputting now.\n<poem>\nNested report\n</poem>\n** {{tact|end}}",
    )
    assert value["variants"]["report"][0]["steps"][1] == {
        "type": "message",
        "text": "Nested report",
    }


def test_annotated_option_becomes_a_condition():
    node = update.parse_step(
        "{{topt|Travel.}} {{Colour|blue|(only after [[The Golem]])}}", [], 1
    )
    assert node == {
        "type": "option",
        "text": "Travel.",
        "condition": "If the player has completed The Golem:",
    }
    issues = []
    node = update.parse_step(
        "{{topt|cond|With a ring equipped:|[Charm] Pick one.}}", issues, 2
    )
    assert node == {
        "type": "option",
        "text": "[Charm] Pick one.",
        "condition": "With a ring equipped:",
    }
    assert issues[0]["reason"] == "Recovered positional option condition"


def test_shared_reply_is_scoped_to_the_speaking_participant_and_keeps_effect_id():
    npcs = {
        name: record(
            name,
            f"==Standard dialogue==\n* {{{{topt|Trade.}}}}\n** '''{name}:''' {name}'s shop.\n** {{{{tact|opens={name}'s Shop}}}}",
        )
        for name in ["Alice", "Bob"]
    }
    quest = record(
        "A quest",
        """{{Transcript list|Alice|Bob}}
==Talking==
* '''Alice:''' Hello.
* {{topt|quest=No|Trade.}}
""",
    )
    pages = {
        name: {"wikitext": "{{Infobox NPC|name=" + name + "|id=" + str(i) + "}}"}
        for i, name in enumerate(npcs, 1)
    }
    enrich_records(npcs, {"A quest": quest}, pages, update.clean)
    option = quest["variants"]["talking"][1]["options"][0]
    assert option["steps"][0]["speaker"] == "Alice"
    assert option["steps"][0]["text"] == "Alice's shop."
    original = npcs["Alice"]["variants"]["standard-dialogue"][0]["options"][0]["steps"][
        -1
    ]
    assert option["steps"][-1]["id"] == original["id"]
    assert not any("_shared" in node for node in walk(quest["variants"]["talking"]))


def test_ambiguous_shared_reply_is_not_guessed():
    npc = record(
        "Alice",
        "==Before==\n* {{topt|Trade.}}\n** '''Alice:''' Before.\n==After==\n* {{topt|Trade.}}\n** '''Alice:''' After.",
    )
    quest = record(
        "A quest",
        "{{Transcript list|Alice}}\n==Talking==\n* '''Alice:''' Hello.\n* {{topt|quest=no|Trade.}}",
    )
    enrich_records({"Alice": npc}, {"A quest": quest}, {}, update.clean)
    assert not quest["variants"]["talking"][1]["options"][0].get("steps")


def test_below_uses_the_matching_line_tail_and_quoted_references_use_source_text():
    value = record(
        "A quest",
        """==Talking==
* {{tselect}}
* {{topt|First}}
** '''Player:''' First.
** {{tact|below}}
* {{topt|Second}}
** '''Player:''' Second.
** '''Other:''' Shared reply.
** {{tact|Continues below from "The final..."}}
* {{topt|Third}}
** '''Other:''' Different opening.
** '''Other:''' Shared reply.
** '''Other:''' The final speech.
** {{qact|The NPC departs.}}
* {{topt|Fourth}}
** '''Other:''' Shared reply.
** {{tact|above}}
""",
    )
    enrich_records({}, {"A quest": value}, {}, update.clean)
    options = value["variants"]["talking"][0]["options"]
    assert follow(value, options[0]["steps"])[1]["text"] == "Shared reply."
    assert follow(value, options[1]["steps"])[2]["text"] == "The final speech."
    assert follow(value, options[3]["steps"])[1]["text"] == "The final speech."


def test_named_section_navigation_keeps_menu_cycles_as_calls():
    value = record(
        "X",
        """==Standard dialogue==
* '''X:''' Hello.
* {{tact|Follow-up options}}
==Follow-up options==
* {{tselect}}
* {{topt|Again}}
** {{tact|Follow-up options}}
""",
    )
    enrich_records({"X": value}, {}, {}, update.clean)
    assert value["variants"]["standard-dialogue"][-1] == {
        "type": "call",
        "branch": "follow-up-options",
    }
    assert value["branches"]["follow-up-options"][0]["options"][0]["steps"][0] == {
        "type": "call",
        "branch": "follow-up-options",
    }


def test_repeated_speech_in_another_section_requires_a_unique_continuation():
    raw = """==First==
* '''Player:''' What did he search for?
* '''Machine:''' Repeat last search.
==Again==
* '''Player:''' What did he search for?
* {{tact|above}}
"""
    value = record("A quest", raw)
    enrich_records({}, {"A quest": value}, {}, update.clean)
    assert follow(value, value["variants"]["again"])[1]["text"] == "Repeat last search."

    value = record(
        "A quest",
        raw.replace(
            "==Again==",
            "==Another==\n* '''Player:''' What did he search for?\n* '''Machine:''' Something else.\n==Again==",
        ),
    )
    enrich_records({}, {"A quest": value}, {}, update.clean)
    assert value["variants"]["again"][-1]["reference"] == "above"

    value = record(
        "A quest", raw.replace("'''Machine:''' Repeat last search.", "{{tact|above}}")
    )
    enrich_records({}, {"A quest": value}, {}, update.clean)
    assert value["variants"]["again"][-1]["reference"] == "above"

    value = record(
        "A quest",
        raw.replace("Repeat last search.", "Repeat last search.\n* {{tact|above}}"),
    )
    enrich_records({}, {"A quest": value}, {}, update.clean)
    assert value["variants"]["again"][-1]["reference"] == "above"


def test_repeated_section_conditions_share_the_explicit_continuation():
    value = record(
        "A quest",
        """==First report==
* {{tcond|If First report was the last report read:}}
** '''Guide:''' We can leave now.
** {{qact|The guide departs.}}
==Second report==
* {{tcond|If Second report was the last report read:}}
** {{tact|above}}
""",
    )
    enrich_records({}, {"A quest": value}, {}, update.clean)
    original = value["variants"]["first-report"][0]["steps"]
    repeated = follow(value, value["variants"]["second-report"][0]["steps"])
    assert repeated == original


def test_explicit_followup_rule_omits_the_topic_just_selected():
    value = record(
        "X",
        """==Standard dialogue==
* {{tselect}}
* {{topt|Tell me about the fleet.}}
** '''X:''' A fine fleet.
** {{tact|Follow-up options}}
* {{topt|Ask some questions.}}
** '''X:''' Ask away.
** {{tact|Follow-up options}}
==Follow-up options==
After a topic ends, the topic just asked about is left out.
* {{tselect}}
* {{topt|Tell me about the fleet.}}
** {{tact|above}}
* {{topt|Ask some questions.}}
** {{tact|above}}
* {{topt|Goodbye.}}
** {{tact|end}}
""",
    )
    enrich_records({"X": value}, {}, {}, update.clean)
    menu = value["branches"]["follow-up-options-without-tellmeaboutthefleet"][0]
    assert [option["text"] for option in menu["options"]] == [
        "Ask some questions.",
        "Goodbye.",
    ]
    assert follow(value, menu["options"][0]["steps"])[0]["npc"] == "Ask away."
    assert not any(node.get("type") == "unavailable" for node in walk(menu["options"]))


def test_same_reply_is_disambiguated_by_its_enclosing_menu():
    value = record(
        "X",
        """==Standard dialogue==
* {{tselect}}
* {{topt|Pay from bank}}
** '''X:''' Bank.
* {{topt|No thanks, keep your money.}}
** '''X:''' Bank refusal.
* {{tselect}}
* {{topt|Yes, okay.}}
** '''X:''' Fine paid.
* {{topt|No thanks, keep your money.}}
** '''X:''' Jail refusal.
==At the door==
* {{tselect}}
* {{topt|Yes, okay.}}
** {{tact|above}}
* {{topt|No thanks, keep your money.}}
** {{tact|above}}
""",
    )
    enrich_records({"X": value}, {}, {}, update.clean)
    refusal = value["variants"]["at-the-door"][0]["options"][1]
    assert follow(value, refusal["steps"])[0]["npc"] == "Jail refusal."


def test_named_and_unnamed_versions_of_the_same_shop_reply_are_equivalent():
    npc = record(
        "Alice",
        """==Before==
* {{topt|Trade.}}
** '''Alice:''' Of course.
** {{tact|(Shop interface opens.)}}
==After==
* {{topt|Trade.}}
** '''Alice:''' Of course.
** {{tact|opens=Alice's Shop}}
""",
    )
    quest = record(
        "A quest",
        "{{Transcript list|Alice}}\n==Talking==\n* '''Alice:''' Hello.\n* {{topt|quest=no|Trade.}}",
    )
    enrich_records({"Alice": npc}, {"A quest": quest}, {}, update.clean)
    assert (
        quest["variants"]["talking"][1]["options"][0]["steps"][-1]["target"]
        == "Alice's Shop"
    )


def test_navigation_does_not_compile_a_loop_without_a_player_step():
    value = record(
        "X",
        """==Standard dialogue==
* '''X:''' First.
* {{tact|Continues after "Second."}}
* '''X:''' Second.
* {{tact|Continues after "First."}}
""",
    )
    enrich_records({"X": value}, {}, {}, update.clean)
    assert not value.get("branches")
    assert not any(
        node.get("type") == "call"
        for node in walk(value["variants"]["standard-dialogue"])
    )


def test_runtime_resume_bindings_use_source_suffixes_and_update_indexes():
    data = {
        "records": {
            "X": {
                "steps": [
                    {"type": "action", "id": "anchor"},
                    {"player": "Reaction."},
                    {"npc": "Resume here."},
                    {"type": "action", "id": "travel", "action": "teleport"},
                ]
            }
        },
        "authoring": {
            "Transcript:X": {"sections": {"standard-dialogue": ["Standard dialogue"]}}
        },
        "index": {"1": [{"page": "Transcript:X", "variants": ["standard-dialogue"]}]},
    }
    apply_bindings(
        data,
        {
            "X": {
                "effects": {"travel": {"target": "A place"}},
                "variants": {
                    "resume": {
                        "variant": "standard-dialogue",
                        "after": "anchor",
                        "skip_player": True,
                    }
                },
            }
        },
    )
    assert data["records"]["X"]["variants"]["resume"] == [
        {"npc": "Resume here."},
        {"type": "action", "id": "travel", "action": "teleport", "target": "A place"},
    ]
    assert data["index"]["1"][0]["variants"] == ["standard-dialogue", "resume"]
    with pytest.raises(ValueError, match="Stale dialogue effect binding"):
        apply_bindings(
            data, {"X": {"effects": {"missing": {"target": "Another place"}}}}
        )
    with pytest.raises(ValueError, match="Stale dialogue resume binding"):
        apply_bindings(
            data,
            {
                "X": {
                    "variants": {
                        "missing": {"variant": "standard-dialogue", "after": "missing"}
                    }
                }
            },
        )
