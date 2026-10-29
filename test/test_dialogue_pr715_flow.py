"""Source-derived routes used by TSPS; hook IDs and reachable content stay intact."""

import json

import config
from scripts.dialogues.hooks import walk


def exports():
    return json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())


def nodes(record, steps, visiting=frozenset()):
    for node in steps:
        yield node
        yield from nodes(record, node.get("steps", []), visiting)
        yield from nodes(record, node.get("options", []), visiting)
        if node.get("type") == "call" and node["branch"] not in visiting:
            yield from nodes(
                record, record["branches"][node["branch"]], visiting | {node["branch"]}
            )


def texts(record, steps):
    return [
        node.get("text", node.get("npc", node.get("player", "")))
        for node in nodes(record, steps)
        if "text" in node or "npc" in node or "player" in node
    ]


def ids(record, steps):
    return {node["id"] for node in nodes(record, steps) if "id" in node}


def test_contact_quiz_keeps_one_shared_run_after_the_answers():
    variant = exports()["Contact!"]["variants"]["kaleef-s-corpse-talking-to-maisa"]
    last_choice = max(
        i for i, node in enumerate(variant) if node.get("type") == "choice"
    )
    assert [node["id"] for node in variant[last_choice + 1 :]] == [
        "IjxRNT",
        "PeJYOi",
        "qEP0VV",
    ]
    for option in variant[last_choice]["options"]:
        assert not any(node.get("type") == "condition" for node in option["steps"])


def test_doric_anvil_yes_reaches_the_quest_start_body_and_ids():
    record = exports()["Doric's Quest"]
    variant = record["variants"][
        "starting-off-attempting-to-use-his-anvils-before-the-quest"
    ]
    yes = next(
        node
        for node in walk(variant)
        if node.get("text") == "Yes, I will get you materials."
    )
    expanded = list(nodes(record, yes["steps"]))
    assert not any(node.get("reference") == "above" for node in expanded)
    speech = texts(record, yes["steps"])
    assert speech[0] == "Yes, I will get you the materials."
    assert "Clay is what I use more than anything" in speech[1]
    assert {"aaa-pe", "qv9cGD", "FgVDzP", "8Tgk_i"} <= ids(record, yes["steps"])
    assert any(
        node.get("action") == "quest_start" or node.get("text") == "Quest complete!"
        for node in expanded
    )


def test_temple_acceptance_and_nested_below_keep_required_ids():
    record = exports()["Temple of the Eye"]
    variant = record["variants"]["an-eye-for-a-favour-talking-to-wizard-persten"]
    yes = next(node for node in walk(variant) if node.get("text") == "Yes.")
    speech = texts(record, yes["steps"])
    assert speech[0] == "Alright, what do you need from me?"
    assert "You'll help? Great!" in speech[1]
    assert {"CD4sRJ", "m_fZw2", "MMRv1P"} <= ids(record, yes["steps"])
    nested = next(
        node
        for node in walk(variant)
        if node.get("text") == "So what are you doing in Al Kharid?"
    )
    expanded = list(nodes(record, nested["steps"]))
    assert {"5x2EJz", "xjLZgp"} <= ids(record, nested["steps"])
    assert "What's a wizard doing in Al Kharid?" in texts(record, nested["steps"])
    assert not any(node.get("reference") == "below" for node in expanded)


def test_corsair_both_chompy_conditions_reach_the_shared_tail():
    record = exports()["The Corsair Curse"]
    variant = record["variants"]["colin-s-curse-returning-to-colin"]
    first, second = variant[2], variant[3]
    assert first["id"] == "q6KWx3" and second["id"] == "Kk6cWa"
    for condition in (first, second):
        expanded = list(nodes(record, condition["steps"]))
        assert not any(node.get("reference") == "below" for node in expanded)
        speech = texts(record, condition["steps"])
        assert any("the curse isn't my fault" in text for text in speech)
        assert speech[-1] == "I'll be on the case."
    assert not any(
        "I've met ogres before" in text for text in texts(record, first["steps"])
    )


def test_restless_ghost_both_abbreviations_reach_the_existing_skull_tail():
    record = exports()["The Restless Ghost"]
    variant = record["variants"][
        "talking-to-the-restless-ghost-while-wearing-the-amulet-of-ghostspeak"
    ]
    for jump_id, prefix in (
        ("6AVit4", "I've been told a certain task"),
        ("P_473A", "Nope. I just know"),
    ):
        jump = next(node for node in walk(variant) if node.get("id") == jump_id)
        assert "reference" not in jump
        speech = texts(record, jump["steps"])
        assert speech[0].startswith(prefix)
        assert "Ooh, thank you. That would be such a great relief!" in speech


def test_routes_are_not_output_subtree_corrections():
    corrections = json.loads(
        (config.DATA_PATH / "dialogues/corrections.json").read_text()
    )
    assert (
        not {"Contact!", "Doric's Quest", "Temple of the Eye", "The Restless Ghost"}
        & corrections.keys()
    )
    assert all(
        "colin-s-curse-returning-to-colin" not in change["path"]
        for change in corrections["The Corsair Curse"]["changes"]
    )
