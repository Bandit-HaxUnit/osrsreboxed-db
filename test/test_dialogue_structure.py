"""Structural source navigation: labels, menus, sections and complement conditions."""

import copy

import pytest

from scripts.dialogues import update
from scripts.dialogues.flow import resolve_navigation
from scripts.dialogues.hooks import annotate, enrich_records, walk


def record(name, raw):
    value = update.gameplay_npc(name, update.parse_npc(name, raw))
    value["source"] = {"page": "Transcript:" + name, "revision": 1}
    return value


def enrich(name, raw):
    value = record(name, raw)
    enrich_records({}, {name: value}, {}, update.clean)
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


def test_long_option_matches_unique_spoken_line_without_articles():
    value = enrich(
        "A quest",
        """==Before==
* '''Smith:''' Hello.
* {{tselect}}
* {{topt|Yes.}}
** '''Player:''' Yes, I will get you the materials.
** '''Smith:''' Bring me clay.
==Attempting==
* '''Smith:''' Not again.
* {{tselect}}
* {{topt|Yes, I will get you materials.}}
** {{tact|above}}
""",
    )
    before = value["variants"]["before"][1]["options"][0]["steps"]
    option = value["variants"]["attempting"][1]["options"][0]
    assert "reference" not in option["steps"][0]
    assert follow(value, option["steps"]) == before


def test_long_option_match_must_be_unique_and_whole_utterance():
    value = enrich(
        "A quest",
        """==Before==
* '''Smith:''' Hello.
* {{tselect}}
* {{topt|One.}}
** '''Player:''' Yes, I will get you the materials.
** '''Smith:''' First.
* {{topt|Two.}}
** '''Player:''' Yes, I will get you the materials.
** '''Smith:''' Second.
==Attempting==
* '''Smith:''' Not again.
* {{tselect}}
* {{topt|Yes, I will get you materials.}}
** {{tact|above}}
""",
    )
    option = value["variants"]["attempting"][1]["options"][0]
    assert option["steps"][0]["reference"] == "above"


def test_long_label_must_introduce_the_target_body_not_match_later_speech():
    value = enrich(
        "A quest",
        """==Before==
* '''Smith:''' Hello.
* {{tselect}}
* {{topt|Unrelated topic}}
** '''Smith:''' A different introduction.
** '''Player:''' Yes, I will get you the materials.
** '''Smith:''' Later reply.
==Attempting==
* '''Smith:''' Not again.
* {{tselect}}
* {{topt|Yes, I will get you materials.}}
** {{tact|above}}
""",
    )
    option = value["variants"]["attempting"][1]["options"][0]
    assert option["steps"][0]["reference"] == "above"


def test_partial_utterance_is_not_an_anchor():
    value = enrich(
        "A quest",
        """==Before==
* '''Smith:''' Hello.
* {{tselect}}
* {{topt|Yes.}}
** '''Player:''' Yes, I will get you lots of materials.
** '''Smith:''' Bring me clay.
==Attempting==
* '''Smith:''' Not again.
* {{tselect}}
* {{topt|Yes, I will get you materials.}}
** {{tact|above}}
""",
    )
    option = value["variants"]["attempting"][1]["options"][0]
    assert option["steps"][0]["reference"] == "above"


def test_nested_below_finds_the_outer_option_body_not_the_next_sibling():
    value = enrich(
        "A quest",
        """==Talk==
* '''Guide:''' Hello.
* {{tselect}}
* {{topt|Who are you?}}
** '''Player:''' Who are you?
** '''Guide:''' A guide.
** {{topt|So what are you doing here?}}
*** {{tact|below}}
** {{topt|See you around.}}
*** {{tact|below}}
* {{topt|What's a guide doing here?}}
** {{tcond|If the player already asked "Who are you?":}}
*** '''Player:''' So what are you doing here?
*** '''Guide:''' Existing reply.
*** {{tact|continues}}
** {{tcond|If the player did not ask "Who are you?":}}
*** '''Player:''' What's a guide doing here?
*** '''Guide:''' Another reply.
*** {{tact|continues}}
** '''Player:''' Later speech.
** {{tact|end}}
* {{topt|See you around.}}
** '''Player:''' See you.
** {{tact|end}}
""",
    )
    inner = value["variants"]["talk"][1]["options"][0]["steps"][2]["options"][0]
    assert "reference" not in inner["steps"][0]
    expanded = follow(value, inner["steps"])
    assert [node.get("type") for node in expanded[:2]] == ["condition", "condition"]
    assert expanded[2]["player"] == "Later speech."
    assert all(node.get("player") != "See you." for node in expanded)


def test_short_label_uses_the_whole_menu_in_the_immediately_following_section():
    value = enrich(
        "A quest",
        """==Talking to Guide==
* '''Guide:''' Hello.
* {{tselect}}
* {{topt|Yes.}}
** {{tact|below}}
* {{topt|No.}}
** '''Player:''' No thanks.
** '''Guide:''' A shame.
** {{tact|end}}
==Talking to Guide after declining==
* '''Guide:''' Changed your mind?
* {{tselect}}
* {{topt|Yes.}}
** '''Player:''' I will help.
** '''Guide:''' Great!
** {{tact|end}}
* {{topt|No.}}
** '''Player:''' Still no.
** {{tact|end}}
""",
    )
    option = value["variants"]["talking-to-guide"][1]["options"][0]
    expanded = follow(value, option["steps"])
    assert expanded[0]["player"] == "I will help."
    assert all(node.get("player") != "No thanks." for node in expanded)


def test_short_label_does_not_reach_across_a_non_adjacent_section_or_guess():
    value = enrich(
        "A quest",
        """==Talking to Guide==
* '''Guide:''' Hello.
* {{tselect}}
* {{topt|Yes.}}
** {{tact|below}}
* {{topt|No.}}
** '''Player:''' No thanks.
** '''Guide:''' A shame.
** {{tact|end}}
==Middle==
* '''Guide:''' Something else.
==Talking to Guide after declining==
* '''Guide:''' Changed your mind?
* {{tselect}}
* {{topt|Yes.}}
** '''Player:''' I will help.
** {{tact|end}}
* {{topt|No.}}
** {{tact|end}}
""",
    )
    option = value["variants"]["talking-to-guide"][1]["options"][0]
    assert option["steps"][0]["reference"] == "below"


def test_below_resumes_the_complementary_condition_tail_without_its_reply():
    value = enrich(
        "A quest",
        """==Returning==
* '''Guide:''' Have you found it?
* '''Player:''' I have news.
* {{tcond|If the player has not completed Helper:}}
** '''Player:''' Alternative reply.
** {{tact|below}}
* {{tcond|If the player has completed Helper:}}
** '''Player:''' Different reply.
** '''Guide:''' Shared tail.
** '''Player:''' Final speech.
""",
    )
    condition = value["variants"]["returning"][2]
    expanded = follow(value, condition["steps"])
    assert expanded[0]["player"] == "Alternative reply."
    assert expanded[1]["text"] == "Shared tail."
    assert expanded[2]["player"] == "Final speech."
    assert all(node.get("player") != "Different reply." for node in expanded)


def test_below_requires_complementary_conditions():
    value = enrich(
        "A quest",
        """==Returning==
* '''Guide:''' Have you found it?
* '''Player:''' I have news.
* {{tcond|If the player has finished First:}}
** '''Player:''' Alternative reply.
** {{tact|below}}
* {{tcond|If the player has finished Second:}}
** '''Player:''' Different reply.
** '''Guide:''' Shared tail.
""",
    )
    condition = value["variants"]["returning"][2]
    assert condition["steps"][1]["reference"] == "below"


def test_repeated_long_option_normalizes_case_and_skips_its_spoken_prefix():
    value = enrich(
        "A quest",
        """==Talk==
* '''Guide:''' Hello.
* {{tselect}}
* {{topt|Yes, ok. Do you know WHY you're a ghost?}}
** '''Player:''' Yes, ok. Do you know WHY you're a ghost?
** '''Guide:''' Nope. I just know I can't do much of anything like this!
** '''Guide:''' Ooh, thank you. That would be such a great relief!
* {{topt|No, you're scary!}}
** {{tact|end}}
==Again==
* '''Guide:''' Look at the amulet.
* {{tselect}}
* {{topt|Yes, ok. Do you know why you're a ghost?}}
** {{tact|above}}
* {{topt|No, you're scary!}}
** {{tact|end}}
""",
    )
    option = value["variants"]["again"][1]["options"][0]
    expanded = follow(value, option["steps"])
    assert (
        expanded[0]["text"]
        == "Nope. I just know I can't do much of anything like this!"
    )
    assert expanded[1]["text"] == "Ooh, thank you. That would be such a great relief!"
    assert all("player" not in node for node in expanded[:1])


def test_bare_above_after_a_unique_npc_line_is_not_guessed():
    value = enrich(
        "A quest",
        """==Talk==
* '''Guide:''' Hello.
* {{tselect}}
* {{topt|Yes, ok. Do you know WHY you're a ghost?}}
** '''Player:''' Yes, ok. Do you know WHY you're a ghost?
** '''Guide:''' Nope. I just know I can't do much of anything like this!
** {{tact|above}}
* {{topt|No, you're scary!}}
** {{tact|end}}
""",
    )
    option = value["variants"]["talk"][1]["options"][0]
    assert option["steps"][2]["reference"] == "above"


def test_reviewed_source_anchor_reuses_the_tail_and_rejects_stale_inputs():
    value = record(
        "A quest",
        """==Talk==
* {{tselect}}
* {{topt|First route}}
** '''Guide:''' Earlier reply.
** '''Player:''' Shared continuation.
** '''Guide:''' The task is accepted.
* {{topt|Other route}}
** '''Guide:''' Different reply.
** {{tact|above}}
""",
    )
    annotate(value["variants"]["talk"], "Transcript:A quest#talk", {})
    menu = value["variants"]["talk"][0]
    destination = menu["options"][0]["steps"][0]["id"]
    source = menu["options"][1]["steps"][1]["id"]
    anchors = {source: {"expected": "above", "after": destination}}
    resolved = copy.deepcopy(value)
    resolve_navigation(resolved, anchors)
    expanded = follow(resolved, resolved["variants"]["talk"][0]["options"][1]["steps"])
    assert expanded[1]["player"] == "Shared continuation."
    assert expanded[2]["text"] == "The task is accepted."
    assert all(node.get("text") != "Earlier reply." for node in expanded)

    for stale in ("source", "destination", "reference", "duplicate"):
        changed = copy.deepcopy(value)
        nodes = {node["id"]: node for node in walk(changed["variants"]["talk"])}
        if stale == "source":
            nodes[source]["id"] = "changed"
        elif stale == "destination":
            nodes[destination]["id"] = "changed"
        elif stale == "reference":
            nodes[source]["reference"] = "below"
        else:
            changed["variants"]["talk"].append(copy.deepcopy(nodes[destination]))
        with pytest.raises(ValueError, match="Stale dialogue navigation anchor"):
            resolve_navigation(changed, anchors)
