"""Focused regressions for the five TSPS PR715 dialogue corrections."""

import json

import config
from scripts.dialogues.corrections import fingerprint
from scripts.dialogues.hooks import walk

NAMES = [
    "Contact!",
    "Doric's Quest",
    "Temple of the Eye",
    "The Corsair Curse",
    "The Restless Ghost",
]


def exports():
    return json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())


def corrections():
    return json.loads((config.DATA_PATH / "dialogues" / "corrections.json").read_text())


def text_values(nodes):
    return [
        node.get("text", node.get("npc", node.get("player", "")))
        for node in walk(nodes)
    ]


def ids(nodes):
    return {node["id"] for node in walk(nodes) if "id" in node}


def test_contact_quiz_conditions_are_guarded_inside_each_answer():
    variant = exports()["Contact!"]["variants"]["kaleef-s-corpse-talking-to-maisa"]
    menu = variant[-1]
    assert menu["type"] == "choice"
    assert len(menu["options"]) == 5
    for option in menu["options"]:
        conditions = [n for n in option["steps"] if n.get("type") == "condition"]
        assert [n["id"] for n in conditions] == ["IjxRNT", "PeJYOi", "qEP0VV"]
    assert not any(n.get("type") == "condition" for n in variant[:-1])


def test_doric_anvil_yes_reaches_the_quest_start_body_and_ids():
    variant = exports()["Doric's Quest"]["variants"][
        "starting-off-attempting-to-use-his-anvils-before-the-quest"
    ]
    yes = variant[1]["options"][0]["steps"][2]["options"][0]["steps"][0]
    assert "reference" not in yes
    assert text_values(yes["steps"])[0] == "Yes, I will get you the materials."
    assert "Clay is what I use more than anything" in text_values(yes["steps"])[1]
    assert {"aaa-pe", "qv9cGD", "FgVDzP", "8Tgk_i"} <= ids(yes["steps"])
    assert any(
        n.get("action") == "quest_start" or n.get("text") == "Quest complete!"
        for n in walk(yes["steps"])
    )


def test_temple_accept_branch_and_nested_below_keep_required_ids():
    record = exports()["Temple of the Eye"]
    accept = record["branches"]["jump-f8a43be52b87efe6"]
    assert accept[0]["player"] == "Alright, what do you need from me?"
    assert "You'll help? Great!" in text_values(accept)[1]
    assert {"CD4sRJ", "m_fZw2", "MMRv1P"} <= ids(accept)
    option = record["variants"]["an-eye-for-a-favour-talking-to-wizard-persten"][2][
        "options"
    ][0]["steps"][6]["options"][0]["steps"]
    assert option[0]["type"] == "condition"
    assert {"5x2EJz", "xjLZgp"} <= ids(option)
    assert "What's a wizard doing in Al Kharid?" in text_values(option)


def test_corsair_colin_tail_is_shared_after_both_chompy_conditions():
    variant = exports()["The Corsair Curse"]["variants"][
        "colin-s-curse-returning-to-colin"
    ]
    assert not any(n.get("reference") == "below" for n in walk(variant))
    first, second = variant[2], variant[3]
    assert first["id"] == "q6KWx3" and second["id"] == "Kk6cWa"
    assert len(first["steps"]) == 1
    assert len(second["steps"]) == 1
    tail = text_values(variant[4:])
    assert any("the curse isn't my fault" in text for text in tail)
    assert tail[-1] == "I'll be on the case."


def test_restless_ghost_above_jumps_expand_the_shared_skull_tail():
    variant = exports()["The Restless Ghost"]["variants"][
        "talking-to-the-restless-ghost-while-wearing-the-amulet-of-ghostspeak"
    ]
    first = variant[4]["options"][1]["steps"][4]["options"][1]["steps"][2]["options"][
        0
    ]["steps"][2]
    second = variant[4]["options"][2]["steps"][2]["options"][0]["steps"][0]
    assert "reference" not in first
    assert "reference" not in second
    assert text_values(first["steps"])[0].startswith("I've been told a certain task")
    assert "Ooh, thank you. That would be such a great relief!" in text_values(
        first["steps"]
    )
    assert text_values(second["steps"])[0].startswith("Nope. I just know")
    assert "Ooh, thank you. That would be such a great relief!" in text_values(
        second["steps"]
    )


def test_generated_records_match_the_five_audited_corrections():
    exported = exports()
    audited = corrections()
    for name in NAMES:
        assert fingerprint(exported[name]) == audited[name]["audited_sha256"], name
