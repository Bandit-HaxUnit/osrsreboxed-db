import json

import config


def nodes(record, steps, visiting=frozenset()):
    for node in steps:
        yield node
        yield from nodes(record, node.get("steps", []), visiting)
        yield from nodes(record, node.get("options", []), visiting)
        if node.get("type") == "call" and node["branch"] not in visiting:
            yield from nodes(
                record, record["branches"][node["branch"]], visiting | {node["branch"]}
            )


def test_source_derived_dialogues_keep_the_audited_content():
    data = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    corrections = json.loads(
        (config.DATA_PATH / "dialogues/corrections.json").read_text()
    )
    fixed = {
        "A Night at the Theatre",
        "Desert Treasure II - The Fallen Empire",
        "Legends' Quest",
        "Misthalin Mystery",
        "Murder Mystery",
        "Tai Bwo Wannai Trio",
        "The Ides of Milk",
        "Vampyre Slayer",
        "Rug Merchant",
        "Shantay",
    }
    assert not fixed & corrections.keys()

    night = data["A Night at the Theatre"]
    crystals = [
        node
        for steps in night["variants"].values()
        for node in nodes(night, steps)
        if node.get("text") == "Can I get those teleport crystals you mentioned?"
    ]
    assert len(crystals) == 22
    for option in crystals:
        assert any(
            node.get("action") == "open_shop"
            and node.get("target") == "Mysterious Stranger (shop)"
            for node in nodes(night, option["steps"])
        )

    dt2 = data["Desert Treasure II - The Fallen Empire"]
    for report, text in [
        ("the-whisperer-true-name-classified", "Race: Siren"),
        ("vardorvis", "Rank: Carnifex Maximus"),
        ("perseriya", "Rank: Praefectus Classis"),
        ("sucellus", "Last Known Location: Ghorrock Prison"),
    ]:
        steps = dt2["variants"][
            "familiar-faces-powering-up-the-golem-machine-" + report
        ]
        expanded = list(nodes(dt2, steps))
        assert any(
            node.get("type") == "message" and text in node.get("text", "")
            for node in expanded
        )
        assert any(node.get("id") == "T24jg_" for node in expanded), report

    repeat = list(
        nodes(
            dt2,
            dt2["variants"][
                "familiar-faces-operating-the-golem-to-find-out-what-dr-banikan-searched"
            ],
        )
    )
    assert any(node.get("player") == "Repeat last search." for node in repeat)
    assert any(
        node.get("type") == "message"
        and node.get("text", "").startswith("Frostenhorn\n")
        for node in repeat
    )

    wgs = data["While Guthix Sleeps"]
    for section in (
        "the-dark-squall-talking-to-silif-after-he-has-been-restored-and-fed",
        "the-dark-squall-talking-to-silif-after-he-returns-to-his-cell",
    ):
        assert any(
            node.get("text") == "Let's go."
            for node in nodes(wgs, wgs["variants"][section])
        ), section

    mystery = data["Misthalin Mystery"]
    steps = mystery["variants"]["the-second-riddle-run-in-with-lacey"]
    for option in next(
        node for node in steps if node.get("prompt") == "Interrupt with answer?"
    )["options"]:
        assert any(
            node.get("text") == "Lacey dies."
            for node in nodes(mystery, option["steps"])
        ), option["text"]

    milk = data["The Ides of Milk"]["variants"][
        "returning-to-cassius-after-sampling-the-milk-resume"
    ]
    assert milk[0]["speaker"] == "Cassius"
    assert any(node.get("id") == "gAirRb" for node in milk)
    assert data["Shantay"]["variants"]["arrested"][0]["npc"].startswith(
        "You'll have to stay in there"
    )

    rug = data["Rug Merchant"]
    assert rug["default"] == "standard-dialogue"
    all_nodes = list(nodes(rug, rug["variants"]["standard-dialogue"]))
    for destination, quest in [
        ("Uzer", "The Golem"),
        ("Menaphos", "Icthlarin's Little Helper"),
        ("Sophanem", "Icthlarin's Little Helper"),
    ]:
        assert any(
            node.get("text") == f"I want to travel to {destination}."
            and node.get("condition") == f"If the player has completed {quest}:"
            for node in all_nodes
        )
    for topic in [
        "Tell me about Ali Morrisane.",
        "Tell me about this magic carpet fleet.",
    ]:
        option = next(
            node for node in all_nodes if node.get("text") == topic and "steps" in node
        )
        calls = [node for node in option["steps"] if node.get("type") == "call"]
        # Calls can live below the source's quest-state conditions.
        if not calls:
            from scripts.dialogues.hooks import walk

            calls = [
                node for node in walk(option["steps"]) if node.get("type") == "call"
            ]
        assert calls
        for call in calls:
            menu = next(
                node for node in nodes(rug, [call]) if node.get("type") == "choice"
            )
            assert topic not in [choice["text"] for choice in menu["options"]]
