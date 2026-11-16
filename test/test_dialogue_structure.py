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


URCHIN = """==Standard dialogue==
===Subsequent dialogue===
* {{tcond|If the player has not met the leader:}}
** '''Lucia:''' Go chat to them!
** {{tact|continue|below}}
* {{tcond|If the player has met the leader:}}
** '''Lucia:''' A fine day for stealing.
** {{tact|continue|below}}
* {{tselect|Select an Option}}
* {{topt|I could do with some information on houses.}}
** {{tselect|Pay 15 valuables for information?}}
** {{topt|Yes.}}
*** {{tcond|If the homeowner is about to leave:}}
**** '''Lucia:''' I hear that [Caius] might be leaving soon.
**** {{tact|continue|below}}
*** {{tcond|If this is the first time:}}
**** '''Lucia:''' Looks like [Caius] isn't home right now. Go quickly!
**** {{tact|continue|below}}
*** {{tcond|If the player already received intel:}}
**** '''Lucia:''' Already forgotten?
**** {{tact|continue|below}}
**** '''Lucia:''' Do you want me to point you in the right direction? {{Anchor|below}}
***** {{tselect|Select an Option}}
***** {{topt|Yes please.}}
****** '''Player:''' Yes please.
****** {{tact|end}}
***** {{topt|I'll find my own way.}}
****** '''Player:''' I'll find my own way.
****** {{tact|end}}
** {{topt|No.}}
*** '''Lucia:''' Suit yourself.
*** {{tact|end}}
* {{topt|I'd better get going.}}
** {{tact|end}}
"""


def test_condition_run_continue_resumes_at_the_anchored_tail_after_the_run():
    """Lucia: `{{tact|continue|below}}` names the `{{Anchor|below}}` that the
    Wiki nests under the last condition; the tail belongs after the whole run."""
    value = record("Lucia", URCHIN)
    resolve_navigation(value)
    steps = value["variants"]["standard-dialogue-subsequent-dialogue"]
    yes = steps[2]["options"][0]["steps"][0]["options"][0]["steps"]
    assert [node.get("type") for node in yes] == [
        "condition",
        "condition",
        "condition",
        None,
    ]
    assert yes[3]["npc"] == "Do you want me to point you in the right direction?"
    assert [option["text"] for option in yes[3]["steps"][0]["options"]] == [
        "Yes please.",
        "I'll find my own way.",
    ]
    for condition in yes[:3]:
        assert condition["steps"][-1]["reference"] == "continue"
        assert not any("npc" in node and "point you" in node["npc"] for node in condition["steps"])
    # A run whose last condition has no anchored tail is left as written: the
    # page's only anchor sits in a later menu, not in that run.
    assert [node.get("type") for node in steps] == ["condition", "condition", "choice"]
    assert steps[1]["steps"][-1]["reference"] == "continue"
    assert "_continue_to" not in str(value) and "_anchors" not in str(value)


def test_condition_run_keeps_a_tail_no_sibling_continue_names():
    value = record(
        "Lucia",
        URCHIN.replace(
            "**** '''Lucia:''' I hear that [Caius] might be leaving soon.\n**** {{tact|continue|below}}",
            "**** '''Lucia:''' I hear that [Caius] might be leaving soon.\n**** {{tact|end}}",
        ).replace(
            "**** '''Lucia:''' Looks like [Caius] isn't home right now. Go quickly!\n**** {{tact|continue|below}}",
            "**** '''Lucia:''' Looks like [Caius] isn't home right now. Go quickly!\n**** {{tact|continue|elsewhere}}",
        ),
    )
    resolve_navigation(value)
    steps = value["variants"]["standard-dialogue-subsequent-dialogue"]
    yes = steps[2]["options"][0]["steps"][0]["options"][0]["steps"]
    assert len(yes) == 3
    assert yes[2]["steps"][-1]["npc"].startswith("Do you want me to point you")


def test_reviewed_source_anchor_can_start_at_a_branch_first_node():
    """`at` starts at the named node: a branch's first node has nothing to resume after."""
    value = record(
        "Lucia",
        """==Talk==
* {{tselect}}
* {{topt|Yes.}}
** {{tcond|If the homeowner is about to leave:}}
*** '''Lucia:''' I hear that [Caius] might be leaving soon.
** {{tcond|If this is the first time:}}
*** '''Lucia:''' Looks like [Caius] isn't home right now.
* {{topt|Yes, don't ask me again.}}
** {{tact|above}}
""",
    )
    annotate(value["variants"]["talk"], "Transcript:Lucia#talk", {})
    menu = value["variants"]["talk"][0]
    destination = menu["options"][0]["steps"][0]["id"]
    source = menu["options"][1]["steps"][0]["id"]
    resolved = copy.deepcopy(value)
    resolve_navigation(resolved, {source: {"expected": "above", "at": destination}})
    expanded = follow(resolved, resolved["variants"]["talk"][0]["options"][1]["steps"])
    assert [node["text"] for node in expanded] == [
        "If the homeowner is about to leave:",
        "If this is the first time:",
    ]
    for invalid in ({"expected": "above"}, {"expected": "above", "at": destination, "after": destination}):
        with pytest.raises(ValueError, match="Invalid dialogue navigation anchor"):
            resolve_navigation(copy.deepcopy(value), {source: invalid})


def test_bare_back_option_on_a_later_menu_page_returns_to_the_previous_page():
    """Lunar Diplomacy's "Prev" before "The trousers" has no `{{tact|previous}}` on the wiki."""
    value = record(
        "Oneiromancer",
        """==Lunar clothing==
* {{tselect|Select an Option}}
* {{topt|The cape}}
** '''Player:''' The cape.
* {{topt|Next}}
** {{tselect|Select an Option}}
** {{topt|Prev}}
*** {{tact|previous}}
** {{topt|Next}}
*** {{tselect|Select an Option}}
*** {{topt|Prev}}
*** {{topt|The ring}}
**** '''Player:''' The ring.
*** {{topt|Exit}}
* {{topt|Previous options...}}
""",
    )
    first = value["variants"]["lunar-clothing"][0]
    second = first["options"][1]["steps"][0]
    third = second["options"][1]["steps"][0]
    previous = [{"type": "jump", "reference": "previous"}]
    assert second["options"][0]["steps"] == previous, "the wiki's own back jump"
    labels = [option["text"] for option in third["options"]]
    assert labels == ["Prev", "The ring", "Exit"]
    assert third["options"][0]["steps"] == previous, "the bare one gets the same"
    assert not third["options"][2].get("steps"), "not every empty option"
    assert not first["options"][2].get("steps"), "a first page has none"


def test_back_option_is_filled_only_when_empty_and_on_a_page_opened_by_a_menu():
    value = record(
        "Banker",
        """==Talk==
* '''Banker:''' Hello.
* {{topt|More options...}}
** '''Banker:''' More?
** {{tselect|Select an Option}}
** {{topt|Previous...}}
** {{topt|Don't mind me.}}
* {{topt|Bank}}
** {{tselect|Select an Option}}
** {{topt|Previous options...}}
*** '''Player:''' Go back.
""",
    )
    menu = value["variants"]["talk"][1]
    after_line = menu["options"][0]["steps"][1]
    # A menu after a line is not a page of the menu above.
    assert not after_line["options"][0].get("steps")
    with_body = menu["options"][1]["steps"][0]
    assert with_body["options"][0]["steps"] == [{"player": "Go back."}]
