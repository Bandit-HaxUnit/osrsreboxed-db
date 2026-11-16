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


def test_veos_shared_travel_uses_the_piscarilius_source_at_every_quest_stage():
    data = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    record = data["Client of Kourend"]
    for variant in [
        "starting-off",
        "starting-off-talking-to-veos-again",
        "returning-to-veos",
        "returning-to-veos-talking-to-veos-again-after-receiving-the-orb",
        "finishing-up",
    ]:
        options = [
            node
            for node in nodes(record, record["variants"][variant])
            if node.get("text") == "Can you take me somewhere?" and "steps" in node
        ]
        assert options, variant
        for option in options:
            travel = list(nodes(record, option["steps"]))
            labels = {node.get("text") for node in travel}
            assert {
                "Travel to Port Sarim.",
                "Travel to Land's End.",
                "Stay where you are.",
            } <= labels
            assert "I'd like to travel to Port Piscarilius, please." not in labels
            assert any(
                node.get("text", "").startswith("As you wish, I hope")
                for node in travel
            )
            for label, reply in [
                ("Travel to Land's End.", "I'd like to travel to Land's End, please."),
                ("Stay where you are.", "Actually I'd like to stay here."),
            ]:
                destination = next(node for node in travel if node.get("text") == label)
                assert any(
                    node.get("player") == reply
                    for node in nodes(record, destination["steps"])
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
    # The Wiki transcript's "he'll he happy" is corrected from capture 4153 (corrections.json).
    gillie = data["The Ides of Milk"]["variants"]["starting-off-talking-to-gillie"]
    assert gillie[1]["options"][2]["steps"][7]["steps"][1]["text"] == (
        "It would be! I'm sure he'll be happy to share some information with you."
    )
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


def test_fortis_house_robbery_urchins_follow_the_live_information_flow():
    """rsprox.net 1105 (Lucia) and 1102 (Ava, Oriana below 50 Thieving)."""
    data = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    for page in ["Lucia", "Oli", "Rufus (Civitas illa Fortis)", "Ava (Civitas illa Fortis)"]:
        record = data[page]
        initial = record["variants"]["standard-dialogue-initial-dialogue"]
        sounds_good = initial[-1]["options"][0]
        assert sounds_good["text"] == "Sounds good."
        flow = list(nodes(record, sounds_good["steps"]))
        texts = [node.get("npc") or node.get("player") or node.get("text") for node in flow]
        assert texts[0] == "Sounds good."
        # Not the decline option's "Suit yourself.": the information flow.
        assert texts[3] == "If the player doesn't have any house keys in their inventory:"
        assert "I could do with some information on houses." not in texts
        free = texts.index(
            "You're new around here. Normally I'd charge 15 valuables for information, but I'm feeling generous."
        )
        # The free information skips the payment menu.
        assert texts.index("If the homeowner is about to leave:") == free + 3
        assert "Do you want me to point you in the right direction?" in texts

        subsequent = record["variants"]["standard-dialogue-subsequent-dialogue"]
        info = subsequent[-1]["options"][0]
        assert info["steps"][0] == {"player": "I could do with some information on houses."}
        pay = [node for node in nodes(record, info["steps"]) if node.get("prompt") == "Pay 15 valuables for information?"]
        assert pay
        yes, again, _ = pay[0]["options"]
        assert [node.get("type") for node in yes["steps"]] == ["condition"] * 3 + [None]
        assert yes["steps"][3]["npc"] == "Do you want me to point you in the right direction?"
        pointer = yes["steps"][3]["steps"][0]
        assert [option["text"] for option in pointer["options"]] == ["Yes please.", "I'll find my own way."]
        again_texts = [node.get("npc") or node.get("text") for node in nodes(record, again["steps"])]
        assert "If the homeowner is about to leave:" in again_texts

        refusal = record["variants"]["standard-dialogue-without-50-thieving"]
        assert refusal[0] == {"npc": "I'm rather busy here, and you don't seem like the thieving type. Beat it!"}
        assert refusal[1] == {"player": "Rude."}
        assert refusal[2]["text"] == "You need 50 Thieving to take part in House Robbery."

    oriana = data["Oriana"]
    refusal = oriana["variants"]["standard-dialogue-without-50-thieving"]
    assert refusal[:2] == [
        {"player": "Hello."},
        {"npc": "Sorry, but I'm rather busy here keeping lookout."},
    ]
    assert refusal[2]["text"] == "You need 50 Thieving to take part in House Robbery."
    initial = oriana["variants"]["standard-dialogue-initial-dialogue"]
    assert {"npc": "Well, that's the nicest thing anyone has ever said to me!"} in initial
    assert {"player": "Right... Well, I'm [player name]. What is it you do around here?"} in initial
    assert {"npc": "Well, I'm the best thief to ever live, ain't I."} in initial


def test_paged_menu_back_options_return_to_the_previous_page():
    """Bare on the wiki, these back options used to end the conversation."""
    data = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    expected = {
        "Lunar Diplomacy": ("Prev", 4),
        "Recipe for Disaster/Freeing Sir Amik Varze": ("Previous...", 2),
        "The Fremennik Isles": ("Previous options...", 1),
        "Observatory Quest": ("~ previous ~", 3),
    }
    for name, (label, count) in expected.items():
        record = data[name]
        flat = {"standard-dialogue": record.get("steps", [])}
        variants = record.get("variants", flat)
        options = [
            node
            for steps in [*variants.values(), *record.get("branches", {}).values()]
            for node in nodes(record, steps)
            if node.get("text") == label and "options" not in node
        ]
        assert len(options) >= count, name
        for option in options:
            steps = option.get("steps", [])
            references = [step.get("reference") for step in steps]
            assert references == ["previous"], (name, option)
