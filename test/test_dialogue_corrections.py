import copy
import hashlib
import json

import pytest

import config
from scripts.dialogues.corrections import apply_corrections, fingerprint
from scripts.dialogues import update
from scripts.dialogues.update import apply_capture_lines


def test_corrections_preserve_ids_additions_deletions_and_indexes():
    data = {
        "records": {"X": {"steps": [{"type": "missing", "id": "old-id"}]}},
        "authoring": {
            "Transcript:X": {"sections": {"standard-dialogue": ["Standard dialogue"]}}
        },
        "index": {"1": [{"page": "Transcript:X", "variants": ["standard-dialogue"]}]},
    }
    replacement = [{"type": "message", "id": "quest:handover", "text": "Done."}]
    corrections = {
        "X": {
            "base_sha256": fingerprint(data["records"]["X"]),
            "changes": [
                {
                    "path": ["records", "X", "steps"],
                    "expected": fingerprint(data["records"]["X"]["steps"]),
                },
                {
                    "path": ["records", "X", "variants"],
                    "expected": None,
                    "value": {"resume": replacement},
                },
                {"path": ["records", "X", "default"], "expected": None, "value": None},
                {
                    "path": ["authoring", "Transcript:X", "sections"],
                    "expected": fingerprint(
                        data["authoring"]["Transcript:X"]["sections"]
                    ),
                    "value": {"resume": ["Resume"]},
                },
                {
                    "path": ["index", "1", 0, "variants"],
                    "expected": fingerprint(["standard-dialogue"]),
                    "value": ["resume"],
                },
            ],
        }
    }
    apply_corrections(data, corrections)
    assert data["records"]["X"] == {
        "variants": {"resume": replacement},
        "default": None,
    }
    assert data["index"]["1"][0]["variants"] == ["resume"]
    assert data["authoring"]["Transcript:X"]["sections"] == {"resume": ["Resume"]}
    replacement[0]["text"] = "Changed source"
    assert data["records"]["X"]["variants"]["resume"][0]["text"] == "Done."


def test_captured_record_requires_absent_source_and_rejects_a_new_wiki_record():
    record = {"steps": [{"npc": "Captured speech."}]}
    correction = {
        "base_sha256": None,
        "changes": [
            {"path": ["records", "Captured"], "expected": None, "value": record}
        ],
    }
    data = {"records": {}}
    apply_corrections(data, {"Captured": correction})
    assert data["records"]["Captured"] == record
    with pytest.raises(ValueError, match="Stale dialogue correction: Captured"):
        apply_corrections(data, {"Captured": correction})

    wiki = {"records": {"Captured": {"steps": [{"npc": "New wiki speech."}]}}}
    before = copy.deepcopy(wiki)
    with pytest.raises(ValueError, match="Stale dialogue correction: Captured"):
        apply_corrections(wiki, {"Captured": correction})
    assert wiki == before


@pytest.mark.parametrize("conflict", ["record", "path", "expected"])
def test_stale_corrections_do_not_partially_apply(conflict):
    data = {"records": {"X": {"steps": [1, 2]}}}
    correction = {
        "base_sha256": fingerprint(data["records"]["X"]),
        "changes": [
            {
                "path": ["records", "X", "steps", 0],
                "expected": fingerprint(1),
                "value": 3,
            },
            {
                "path": ["records", "X", "steps", 1],
                "expected": fingerprint(2),
                "value": 4,
            },
        ],
    }
    if conflict == "record":
        data["records"]["X"]["steps"][1] = 5
    elif conflict == "path":
        correction["changes"][1]["path"] = ["records", "X", "missing", 0]
    else:
        correction["changes"][1]["expected"] = fingerprint(5)
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="Stale dialogue correction: X"):
        apply_corrections(data, {"X": correction})
    assert data == before


def test_dump_applies_corrections_before_writing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "dialogues.update",
            "--offline",
            "--out",
            str(tmp_path / "npc-dialogues.json"),
        ],
    )
    monkeypatch.setattr(update, "read_cache", lambda path: {})
    monkeypatch.setattr(update, "shop_index", lambda: {})
    monkeypatch.setattr(update, "slayer_masters", lambda: set())
    monkeypatch.setattr(update, "apply_bindings", lambda *args: None)
    monkeypatch.setattr(
        update,
        "save",
        lambda *args, **kwargs: pytest.fail("Published before checking corrections"),
    )

    def stale(data, corrections):
        assert corrections
        raise ValueError("Stale dialogue correction")

    monkeypatch.setattr(update, "apply_corrections", stale)
    with pytest.raises(ValueError, match="Stale dialogue correction"):
        update.main()
    assert not list(tmp_path.iterdir())


def test_captured_ides_line_replaces_the_wiki_typo():
    dialogues = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    variant = dialogues["The Ides of Milk"]["variants"][
        "starting-off-talking-to-gillie"
    ]
    text = json.dumps(variant)
    assert "he'll be happy" in text
    assert "he'll he happy" not in text


def test_prince_ali_rescue_plays_the_revision_242_capture():
    variants = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())[
        "Prince Ali Rescue"
    ]["variants"]
    aggie = json.dumps(variants["preparations-for-rescue-talking-to-aggie"])
    assert (
        "Yes, I can. I see you already have the ingredients - the water, flour,"
        " ashes and redberries. Would you like me to mix some for you now?"
    ) in aggie
    assert "Yes I can. I see you already have the ingredients." not in aggie

    leela = variants["starting-out-talking-to-leela"]
    assert [step.get("player") or step.get("text") for step in leela[:2]] == [
        "You must be Leela. Your father sent me to help rescue Prince Ali.",
        "Yes, he sent word ahead that you'd be coming. Are you aware of the plan?",
    ]
    prepared = leela[2]
    assert prepared["type"] == "condition"
    assert prepared["text"] == "If the player has the disguise, the key and a rope:"
    assert [step.get("player") or step.get("text") for step in prepared["steps"]] == [
        "Yes. In fact, I already have everything we need.",
        "Good work. Now, before breaking the Prince out, you'll need to find a way"
        " to deal with his personal guard. He's talkative, so try to find a"
        " weakness. Remember, we don't want any unneeded violence.",
        "Alright. I'll go have a chat to this guard.",
        None,
    ]
    assert prepared["steps"][-1] == {"type": "end"}
    # The unprepared first visit still explains the plan.
    assert leela[3]["player"].startswith("I need to obtain a copy of the key")

    # Live, Joe takes the second and third beers straight after the first; the
    # "Not too drunk?" question leads only into his one-beer reply.
    record = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())[
        "Prince Ali Rescue"
    ]
    for steps in [
        record["variants"]["executing-the-rescue-talking-to-joe"][2]["options"][0][
            "steps"
        ],
        record["branches"]["jump-c2dcd1ef49d2a376"],
    ]:
        assert steps[4]["text"] == "That was perfect! I can't thank you enough."
        fewer, more = steps[5], steps[6]
        assert fewer["text"] == "If the player has less than three beers:"
        assert fewer["steps"][0] == {
            "player": "How are you? Still okay? Not too drunk?"
        }
        assert more["text"] == "If the player has two more beers:"
        assert more["steps"][0] == {
            "player": "Would you care for another beer, my friend?"
        }


def test_witchs_house_follows_the_revision_242_capture():
    dialogues = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    variants = dialogues["Witch's House"]["variants"]
    start = variants["getting-started"][2]["options"][0]["steps"][3]["options"][0]
    assert start["steps"][1]["text"] == "Thanks, mister!"
    boy = dialogues["Boy"]["variants"]["before-witch-s-house"]
    assert boy[2]["options"][0]["steps"][2]["options"][0]["steps"][1] == {
        "npc": "Thanks, mister!"
    }
    # The locked back door is a game message the plugin sends; the transcript is the
    # player's live line alone.
    assert variants[
        "the-witch-s-house-attempting-to-open-the-garden-door-without-unlocking-it"
    ] == [
        {
            "player": "It's locked. That's strange - I can't see any kind of lock"
            " or handle to open it..."
        }
    ]
    gate = variants["the-witch-s-house-attempting-to-open-the-gate-without-correct-gloves"]
    assert gate[0]["text"] == "As your hands touch the gate you feel a shock."
    form = variants["the-ball-killing-the-first-form"]
    assert form[0]["text"] == "The shapeshifters' body begins to deform!"

    # Node-level edits only: no generated variant or branch is supplied whole.
    corrections = json.loads(
        (config.DATA_PATH / "dialogues" / "corrections.json").read_text(encoding="utf-8")
    )
    for name in ("Witch's House", "Boy"):
        for change in corrections[name]["changes"]:
            assert len(change["path"]) > 4, change["path"]
            assert not isinstance(change.get("value"), (list, dict)), change["path"]

    # The back door is a source input applied to the cached Wiki revision before
    # parsing, not a post-parse edit of the generated variant.
    assert not any(
        "garden-door-without-unlocking-it" in str(key)
        for change in corrections["Witch's House"]["changes"]
        for key in change["path"]
    )
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Witch's House"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Witch's House"
    ]
    assert source["revision"] == page["revision"]
    lines = page["wikitext"].splitlines()
    for fix in source["lines"]:
        assert hashlib.sha256(lines[fix["line"] - 1].encode()).hexdigest() == fix["sha256"]
    raw = apply_capture_lines("Witch's House", page["wikitext"], source, page["revision"])
    assert "This door is locked." not in raw
    assert "It's locked. That's strange" in raw
    # Applying it twice from the same inputs is identical; a moved revision stops the dump.
    assert raw == apply_capture_lines("Witch's House", page["wikitext"], source, page["revision"])
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Witch's House", page["wikitext"], source, page["revision"] + 1)


def test_biohazard_follows_the_revision_242_capture():
    variants = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())[
        "Biohazard"
    ]["variants"]
    # Before the wall is crossed, Elena points back to Jerico (capture tick 29).
    assert variants["getting-started-talking-to-elena-again"] == [
        {"player": "Hello Elena."},
        {"type": "line", "speaker": "Elena", "text": "Hello friend. Any luck finding my distillator?"},
        {"player": "No, I'm afraid not."},
        {
            "type": "line",
            "speaker": "Elena",
            "text": "Speak to Jerico, he might be able to help you cross the wall. He lives"
            " in a house south east of here, north of the chapel.",
        },
    ]
    # The mud patch stays under the first conversation with Elena.
    assert "getting-started-talking-to-elena-trying-to-dig-in-the-mud-patch" in variants
    assert variants["getting-started-talking-to-jerico-again"][:2] == [
        {"player": "Hello Jerico."},
        {"type": "line", "speaker": "Jerico", "text": "Hello again. Have you spoken to Omart yet?"},
    ]
    # Talking to Jerico after Omart already opened with the greeting; it gains no second one.
    after_omart = variants["getting-started-talking-to-jerico-after-talking-to-omart"]
    assert [step.get("player") for step in after_omart[:2]] == ["Hello Jerico.", None]
    assert variants["visiting-south-east-varrock-talking-to-asyff"][1] == {
        "player": "Errr... what are you saying exactly?"
    }

    # Source inputs over the cached revision, not edits of the generated record.
    corrections = json.loads(
        (config.DATA_PATH / "dialogues" / "corrections.json").read_text(encoding="utf-8")
    )
    assert "Biohazard" not in corrections
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Biohazard"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Biohazard"
    ]
    assert source["revision"] == page["revision"]
    lines = page["wikitext"].splitlines()
    for fix in source["lines"]:
        assert hashlib.sha256(lines[fix["line"] - 1].encode()).hexdigest() == fix["sha256"]
    raw = apply_capture_lines("Biohazard", page["wikitext"], source, page["revision"])
    assert raw == apply_capture_lines("Biohazard", page["wikitext"], source, page["revision"])
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Biohazard", page["wikitext"], source, page["revision"] + 1)


def test_shadow_of_the_storm_golem_exchange_plays_once_with_both_sigil_branches():
    dialogues = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    source = json.loads(
        (config.DATA_PATH / "dialogues/quest-pages.json").read_text()
    )["Transcript:Shadow of the Storm"]["wikitext"]
    variant = dialogues["Shadow of the Storm"]["variants"][
        "performing-the-ritual-talking-to-the-golem-after-reprogramming"
    ]

    def spoken(node):
        return node.get("text") or node.get("player") or node.get("npc") or ""

    def texts(steps):
        for node in steps:
            yield spoken(node)
            yield from texts(node.get("steps", []))
            for option in node.get("options", []):
                yield from texts(option.get("steps", []))

    exchange = [
        "I sensed a great darkness, as of a demon revelling in its moment of triumph.",
        "And now this sandstorm appears, the likes of which I have not seen in three thousand years. What can it mean?",
        "Denath was Agrith-Naar all along! We've accidentally helped him get back to his own dimension!",
        "It is a terrible thing for a demon to be victorious. I wish there was something I could do to rectify the situation.",
        "You could help me summon the demon again so I could kill him!",
        "What are we waiting for? What do I need to do?",
    ]
    assert [spoken(node) for node in variant[:6]] == exchange
    assert [node.get("text") for node in variant[6:]] == [
        "While having a demonic sigil:",
        "Without a demonic sigil:",
    ]
    played = list(texts(variant))
    for line in exchange + ["I need to get you a demonic sigil.", "I will wait."]:
        assert played.count(line) == 1, line
    assert [text for text in texts(variant[6]["steps"]) if text] == [
        "Take this demonic sigil and go through the portal."
    ]
    assert [text for text in texts(variant[7]["steps"]) if text] == [
        "I need to get you a demonic sigil.",
        "I will wait.",
    ]
    assert all(text in source for text in played if text)


def test_audited_variants_are_indexed():
    index = json.loads((config.DOCS_PATH / "npc-dialogue-index.json").read_text())
    authoring = json.loads(
        (config.DATA_PATH / "dialogues/authoring-index.json").read_text()
    )
    for name, variant in [
        ("Shantay", "arrested"),
        ("The Ides of Milk", "returning-to-cassius-after-sampling-the-milk-resume"),
    ]:
        page = "Transcript:" + name
        assert variant in authoring[page]["sections"]
        assert any(
            entry["page"] == page and variant in entry["variants"]
            for entries in index.values()
            for entry in entries
        )


def test_cache_bound_shared_npc_variants_are_indexed():
    index = json.loads((config.DOCS_PATH / "npc-dialogue-index.json").read_text())
    for npc_id in ("913", "1987"):
        assert len(index[npc_id]) == 1
        entry = index[npc_id][0]
        assert entry["page"] == "Transcript:Shadow of the Storm"
        assert "to-uzer-talking-to-evil-dave" in entry["variants"]
        assert "after-killing-agrith-naar-evil-dave" in entry["variants"]
    assert index["15839"] == [
        {
            "page": "Transcript:The Blood Moon Rises",
            "variants": ["pre-release-dialogue", "starting-out"],
        }
    ]


def test_correction_inserts_a_node_before_its_anchor_and_rejects_a_stale_anchor():
    steps = [{"npc": "One."}, {"type": "message", "text": "Two.", "id": "keep"}]
    data = {"records": {"X": {"steps": copy.deepcopy(steps)}}}
    branch = {"type": "condition", "text": "If asked:", "steps": [], "id": "x:new"}
    correction = {
        "base_sha256": fingerprint(data["records"]["X"]),
        "changes": [
            {
                "path": ["records", "X", "steps", 1],
                "expected": fingerprint(steps[1]),
                "insert": branch,
            }
        ],
    }
    apply_corrections(data, {"X": correction})
    assert [s.get("id") for s in data["records"]["X"]["steps"]] == [
        None,
        "x:new",
        "keep",
    ]
    branch["id"] = "mutated"
    assert data["records"]["X"]["steps"][1]["id"] == "x:new"

    fresh = {"records": {"X": {"steps": copy.deepcopy(steps)}}}
    fresh["records"]["X"]["steps"][1]["text"] = "Changed upstream."
    correction["base_sha256"] = fingerprint(fresh["records"]["X"])
    with pytest.raises(ValueError, match="Stale dialogue correction: X"):
        apply_corrections(fresh, {"X": correction})
    off_end = {"records": {"X": {"steps": copy.deepcopy(steps)}}}
    correction["base_sha256"] = fingerprint(off_end["records"]["X"])
    correction["changes"][0]["path"] = ["records", "X", "steps", 5]
    correction["changes"][0]["expected"] = None
    with pytest.raises(ValueError, match="Stale dialogue correction: X"):
        apply_corrections(off_end, {"X": correction})


def test_dragon_slayer_i_follows_the_revision_242_capture():
    path = config.DOCS_PATH / "npc-dialogues.json"
    record = json.loads(path.read_text(encoding="utf-8"))["Dragon Slayer I"]
    text = json.dumps(record, ensure_ascii=False)
    assert "with each of them taking one piece" in text
    assert "which each of them taking" not in text
    assert "Well, you're braver than I!" in text
    assert "a braver man than I" not in text
    assert "Of course! How does 2,000 coins sound?" in text
    assert "I'm sure the work needed to do on it" not in text
    needle = "Ask me about Melzar's map piece again when you have enough free inventory space for the key."
    key_nodes = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("id") == "dragon-slayer-i:melzar-key-no-space":
                key_nodes.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(record)
    assert len(key_nodes) == 2  # the variant and the shared branch
    for node in key_nodes:
        assert node["type"] == "condition"
        assert node["steps"][0]["text"] == needle
        # dragon.txt:23987: after the reply the Guildmaster's follow-up menu opens again.
        assert node["steps"][-1] == {
            "type": "jump",
            "reference": "other",
            "id": "dragon-slayer-i:melzar-key-no-space-menu",
        }


def _list_correction(items, changes):
    data = {"records": {"X": {"steps": list(items)}}}
    return data, {
        "X": {"base_sha256": fingerprint(data["records"]["X"]), "changes": changes}
    }


def _at(index, anchor, **change):
    expected = None if anchor is None else fingerprint(anchor)
    return {"path": ["records", "X", "steps", index], "expected": expected, **change}


def test_correction_indices_name_the_record_before_any_change_in_any_order():
    items = ["a", "b", "c"]
    for changes in (
        [_at(1, "b", insert="NEW"), _at(2, "c", value="C")],
        [_at(2, "c", value="C"), _at(1, "b", insert="NEW")],
    ):
        data, corrections = _list_correction(items, changes)
        apply_corrections(data, corrections)
        assert data["records"]["X"]["steps"] == ["a", "NEW", "b", "C"]
    for changes in ([_at(1, "b"), _at(2, "c")], [_at(2, "c"), _at(1, "b")]):
        data, corrections = _list_correction(items, changes)
        apply_corrections(data, corrections)
        assert data["records"]["X"]["steps"] == ["a"]
    data, corrections = _list_correction(items, [_at(0, "a"), _at(2, "c", value="C")])
    apply_corrections(data, corrections)
    assert data["records"]["X"]["steps"] == ["b", "C"]
    # A node's own edit goes before inserts at its index; inserts there keep their listed order.
    data, corrections = _list_correction(
        items, [_at(1, "b", insert="X1"), _at(1, "b"), _at(1, "b", insert="X2")]
    )
    apply_corrections(data, corrections)
    assert data["records"]["X"]["steps"] == ["a", "X1", "X2", "c"]
    data, corrections = _list_correction(items, [_at(3, None, insert="END")])
    apply_corrections(data, corrections)
    assert data["records"]["X"]["steps"] == ["a", "b", "c", "END"]


@pytest.mark.parametrize(
    "changes, message",
    [
        ([_at(-1, None, insert="NEW")], "Stale"),
        ([_at(-1, "c", value="C")], "Stale"),
        ([_at(3, None, value="D")], "Stale"),
        ([_at(3, None)], "Stale"),
        ([_at(1, "b", insert="NEW", value="B")], "Stale"),
        ([_at(1, "b", value="B"), _at(1, "b")], "Conflicting"),
    ],
)
def test_correction_rejects_unanchored_or_conflicting_list_changes(changes, message):
    data, corrections = _list_correction(["a", "b", "c"], changes)
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match=f"{message} dialogue correction: X"):
        apply_corrections(data, corrections)
    assert data == before


def test_correction_rejects_an_edit_inside_a_replaced_node():
    data = {"records": {"X": {"steps": [{"text": "a"}]}}}
    node = data["records"]["X"]["steps"][0]
    corrections = {
        "X": {
            "base_sha256": fingerprint(data["records"]["X"]),
            "changes": [
                {
                    "path": ["records", "X", "steps", 0],
                    "expected": fingerprint(node),
                    "value": {"text": "b"},
                },
                {
                    "path": ["records", "X", "steps", 0, "text"],
                    "expected": fingerprint("a"),
                    "value": "c",
                },
            ],
        }
    }
    with pytest.raises(ValueError, match="Conflicting dialogue correction: X"):
        apply_corrections(data, corrections)


def test_crab_quest_capture_lines_insert_and_reword_before_parsing():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Crab Quest"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Crab Quest"
    ]
    assert source["revision"] == page["revision"]
    raw = apply_capture_lines("Crab Quest", page["wikitext"], source, page["revision"])
    lines = raw.splitlines()
    # The inserted line lands ahead of its anchor, which is kept unchanged.
    tune = lines.index("* '''Crab:''' We can make a great tune with this!")
    assert lines[tune + 1].startswith("* '''Crab:''' Oh no... I can't easily play 13 different shells")
    assert len(lines) == len(page["wikitext"].splitlines()) + 1
    assert "how the practice is going." in raw and "how the practise is going." not in raw
    assert "But anyway, we are done here." in raw and "anyways" not in raw
    assert raw == apply_capture_lines("Crab Quest", page["wikitext"], source, page["revision"])
    # An anchor whose line moved stops the dump, inserts included.
    moved = "\n" + page["wikitext"]
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Crab Quest", moved, source, page["revision"])
    with pytest.raises(ValueError, match="Invalid dialogue capture source"):
        apply_capture_lines(
            "Crab Quest", page["wikitext"],
            {**source, "lines": [{**source["lines"][0], "insert_before": ["a\nb"]}]},
            page["revision"],
        )
    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    assert "We can make a great tune with this!" in json.dumps(exported["Crab Quest"])


def test_twilights_promise_capture_lines_add_the_requirements_ending():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Twilight's Promise"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Twilight's Promise"
    ]
    assert source["revision"] == page["revision"]
    raw = apply_capture_lines("Twilight's Promise", page["wikitext"], source, page["revision"])
    assert raw == apply_capture_lines("Twilight's Promise", page["wikitext"], source, page["revision"])
    # The captured comma after "Well", and the capitalised Colosseum.
    assert "'''Player:''' Well, this doesn't sound totally orthodox" in raw
    assert "Well this doesn't sound totally orthodox" not in raw
    assert "Where can I find the colosseum?" not in raw
    # Lines the capture doesn't play stay as cached.
    assert "Well rules are rules, I'm afraid." in raw
    # The unmet-requirements ending goes ahead of the Wiki's, which moves one level down.
    lines = raw.splitlines()
    unmet = lines.index(
        "* {{tcond|If the player does not meet all of the requirements to start The Heart of Darkness:}}"
    )
    assert lines[unmet + 3] == (
        "** '''Prince Itzla Arkan:''' Thank you, iknami. Timoiva for now, and may the sun light your way."
    )
    assert lines[unmet + 7].startswith("** '''Prince Itzla Arkan:''' Word has been sent to mother")
    assert len(lines) == len(page["wikitext"].splitlines()) + 7
    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    ending = exported["Twilight's Promise"]["variants"][
        "the-twilight-emissaries-after-defeating-the-cultists"
    ]
    conditions = [step for step in ending if step.get("type") == "condition"]
    assert [c["text"].startswith("If the player does not meet") for c in conditions] == [True, False]
    assert conditions[0]["steps"][-2] == {
        "type": "action", "text": "Congratulations! Quest complete!", "id": conditions[0]["steps"][-2]["id"],
    }
    assert conditions[1]["steps"][-1]["type"] == "choice"


def test_sea_slug_capture_lines_box_the_torch_and_drop_the_repeat():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Sea Slug"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Sea Slug"
    ]
    assert source["revision"] == int(page["revision"])
    raw = apply_capture_lines("Sea Slug", page["wikitext"], source, int(page["revision"]))
    assert raw == apply_capture_lines("Sea Slug", page["wikitext"], source, int(page["revision"]))
    lines = raw.splitlines()
    # Kennith's after-the-wall exchange plays once (the Wiki repeats its first three lines).
    assert sum("Kennith, I've made an opening in the wall." in line for line in lines) == 1
    # The free-space branch gets the torch box the no-space branch already had, ahead of the hand-out.
    free = lines.index("* {{tcond|If the player has one free space in their in their inventory:}}")
    assert lines[free + 1] == "** {{tbox|pic=Unlit torch detail.png|Bailey gives you a torch.}}"
    assert lines[free + 2] == "** {{tact|receives=an unlit torch}}"
    assert "** {{mes|I need to get closer to use that.}}" in lines
    assert "I need to get closer to that." not in raw
    # The dropped repeat leaves three blank lines; the box adds one.
    assert len(lines) == len(page["wikitext"].splitlines()) + 1
    moved = "\n" + page["wikitext"]
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Sea Slug", moved, source, int(page["revision"]))
    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())["Sea Slug"]
    after_wall = exported["variants"]["freeing-kennith-talking-to-kennith-after-making-a-hole-in-the-wall"]
    clear = next(step for step in after_wall if step.get("text") == "If there are no sea slugs or fishermen nearby:")
    assert [step.get("player") or step.get("text") for step in clear["steps"]][:3] == [
        "Kennith, I've made an opening in the wall. You can come out through there.",
        "Are there any sea slugs on the other side?",
        "Not one.",
    ]
    assert clear["steps"][3]["text"] == "How will I get downstairs?"


def test_observatory_quest_follows_the_revision_242_capture():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Observatory Quest"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Observatory Quest"
    ]
    assert source["revision"] == page["revision"]
    raw = apply_capture_lines("Observatory Quest", page["wikitext"], source, page["revision"])
    assert raw == apply_capture_lines("Observatory Quest", page["wikitext"], source, page["revision"])
    assert "Just a plain stove. Nothing there." in raw and "Nothing here." not in raw
    lines = raw.splitlines()
    # Two lines are emptied and one is inserted, so the transcript is a line longer.
    assert len(lines) == len(page["wikitext"].splitlines()) + 1
    # Handing over the mould starts at the professor's question (capture tick 1013).
    mould = lines.index("==Returning with the lens mould==")
    assert lines[mould + 4 : mould + 7] == ["", "", "** '''Observatory professor:''' Did you bring me the mould?"]
    # The molten-glass hand-in keeps its own two lines.
    glass = lines.index("==Returning with molten glass==")
    assert lines[glass + 4] == "** '''Observatory professor:''' How are you getting on finding me some molten glass?"
    # The professor asks for the lens before it is handed over (tick 1038).
    lens = lines.index("==Returning with the observatory lens==")
    assert lines[lens + 4] == "** '''Observatory professor:''' Is the lens finished?"
    assert lines[lens + 5] == "** '''Player:''' Yes, here it is. You may as well take this mould too."
    # The hand-over sits under its menu option, so Treasure Trails is the menu's other option.
    assert lines[lens + 13] == "*** {{tact|end}}"
    assert lines[lens + 14] == "* {{topt|quest=no|Talk about Treasure Trails.}}"
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Observatory Quest", "\n" + page["wikitext"], source, page["revision"])

    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    variants = exported["Observatory Quest"]["variants"]
    returning = json.dumps(variants["returning-with-the-lens-mould"])
    assert "How are you getting on finding me some molten glass?" not in returning
    assert "Did you bring me the mould?" in returning
    lens_variant = variants["returning-with-the-observatory-lens"]
    assert "Is the lens finished?" in json.dumps(lens_variant)
    menu = next(step for step in lens_variant if step.get("type") == "choice")
    assert [option["text"] for option in menu["options"]] == [
        "Talk about the Observatory quest.", "Talk about Treasure Trails."
    ]
    assert variants["inspecting-the-goblin-stove"][0]["text"] == "Just a plain stove. Nothing there."
    # The step ids TSPS binds.
    text = json.dumps(variants)
    # The lens hand-over and the closing box sit one level deeper, so their ids moved (HgpGGr, vj7Nry).
    for step_id in ("JH15Z2", "URgSXm", "HgpGGr", "vj7Nry", "Y5Z4-D", "Lmq76H"):
        assert f'"{step_id}"' in text


def test_plague_city_capture_lines_add_jethick_and_the_clerk():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Plague City"]
    page = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Plague City"
    ]
    assert source["revision"] == int(page["revision"])
    raw = apply_capture_lines("Plague City", page["wikitext"], source, int(page["revision"]))
    assert raw == apply_capture_lines("Plague City", page["wikitext"], source, int(page["revision"]))
    lines = raw.splitlines()
    # The inserts are the Wiki's own lines from its other sections; nothing new is worded.
    cached = set(page["wikitext"].splitlines())
    for fix in source["lines"]:
        for line in fix.get("insert_before", []):
            assert line.lstrip("*") in {other.lstrip("*") for other in cached} or "{{t" in line
    # 10 intro lines, the 12-line book offer (the section's end becomes a blank line), the clerk's
    # option and its jump.
    assert len(lines) == len(page["wikitext"].splitlines()) + 10 + 12 + 2
    moved = "\n" + page["wikitext"]
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Plague City", moved, source, int(page["revision"]))
    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())["Plague City"]["variants"]
    # Jethick's first talk with the picture (capture ticks 372-380) opens with the king conversation.
    first = exported["finding-elena-talking-to-jethick-after-getting-elena-s-picture"][0]
    assert [step.get("player") for step in first["steps"]][1] == "How come?"
    assert first["steps"][-1]["text"].startswith("Anyway, you clearly didn't come here to talk about kings.")
    # Again before delivering the book (397-405), he still offers it.
    again = exported[
        "finding-elena-talking-to-jethick-after-getting-elena-s-picture-talking-to-jethick-again-before-delivering-the-book"
    ]
    assert again[-2]["text"].startswith("I don't suppose you could run me a little errand")
    assert [option["text"] for option in again[-1]["options"]] == [
        "Yes, I'll return it for you.", "No, I don't have time for that.",
    ]
    # The clerk's menu after "Rather you than me!" has the third option (597-602).
    clerk = exported["finding-elena-talking-to-the-clerk-before-getting-permission-to-speak-to-bravek"]
    menu = clerk[1]["options"][0]["steps"][2]
    assert [option["text"] for option in menu["options"]] == [
        "I'll try asking them then.",
        "Surely you don't let them run everything for you?",
        "This is urgent though! Someone's been kidnapped!",
    ]


def test_historian_minas_reports_follow_the_captures():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )["Historian Minas"]
    page = json.loads((config.DATA_PATH / "dialogues/wiki-pages.json").read_text())[
        "Transcript:Historian Minas"
    ]
    assert source["revision"] == page["revision"]
    raw = apply_capture_lines("Historian Minas", page["wikitext"], source, page["revision"])
    assert raw == apply_capture_lines("Historian Minas", page["wikitext"], source, page["revision"])
    lines = raw.splitlines()
    # Curse of the Empty Lord gains its three lamp lines and Making History those three and its
    # lamp box; every other fix replaces a line.
    assert len(lines) == len(page["wikitext"].splitlines()) + 7
    # The Wiki writes these narration boxes as bare prose, which parsed as unavailable markers.
    assert lines.count("*** {{tbox|You receive an old lamp.}}") == 4
    assert (
        "*** {{tbox|The historian pulls out his writing implements and listens while you explain the whole story....}}"
        in lines
    )
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines("Historian Minas", "\n" + page["wikitext"], source, page["revision"])

    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())["Historian Minas"]

    def find(steps, step_id):
        for step in steps or []:
            if step.get("id") == step_id:
                return step
            found = find(step.get("steps"), step_id)
            for option in step.get("options") or []:
                found = found or find(option.get("steps"), step_id)
            if found:
                return found
        return None

    def flow(step_id):
        return [
            step.get("player") and ("player", step["player"])
            or step.get("npc") and ("npc", step["npc"])
            or (step["type"], step.get("text"))
            for step in find(exported["steps"], step_id)["steps"]
        ]

    # Hazeel Cult: the box comes before Minas's closing line, so the report reaches it.
    hazeel = flow("9_Sehd")
    assert hazeel[-2] == (
        "message",
        "The historian pulls out his writing implements and listens while you explain the whole story....",
    )
    assert hazeel[-1] == ("npc", "How exciting, I'll get a display put up immediately. Display number 7, 5th Age, year 7.")
    assert "Zamorakian lord" in hazeel[-3][1]
    # Shield of Arrav, Merlin's Crystal and Making History end on the lamp box, like Defender of Varrock.
    for step_id in ("QqHvp-", "RaNFxc", "4Ij9Rt", "jeha67"):
        assert flow(step_id)[-1] == ("message", "You receive an old lamp.")
    assert flow("QqHvp-")[2] == ("player", "Erm, yes... Anyway, I managed to get half the Shield of Arrav back.")
    # The two Salve reports as the captures play them.
    assert flow("3q8-VQ")[0] == (
        "player", "I discovered some disturbing yet heroic information about the vampyres of Morytania."
    )
    assert flow("dHMXRQ")[-1] == ("npc", "How fascinating. I'll have the display updated. Number 23, 4th Age, year 1100-1200.")
    assert flow("0sSqOl")[-1] == ("npc", "You're welcome!")
    assert flow("IqnOid")[2] == ("player", "Don't worry. I put a stop to their plots.")
    # No report closes on an unavailable marker any more.
    reports = find(exported["steps"], "S57fCr")
    assert reports is not None
    for step_id in ("S57fCr", "QqHvp-", "oGD9-i", "GpIr8R", "RaNFxc", "EZzFyt", "3q8-VQ", "dHMXRQ",
                    "Yq_0tv", "4Ij9Rt", "SJoct1", "0sSqOl", "9_Sehd", "IqnOid", "jeha67"):
        assert '"unavailable"' not in json.dumps(find(exported["steps"], step_id))


def test_ghosts_ahoy_follows_the_revision_242_capture():
    sources = json.loads(
        (config.DATA_PATH / "dialogues" / "capture-sources.json").read_text(encoding="utf-8")
    )
    bindings = json.loads(
        (config.DATA_PATH / "dialogues" / "runtime-bindings.json").read_text(encoding="utf-8")
    )
    quest = json.loads((config.DATA_PATH / "dialogues/quest-pages.json").read_text())[
        "Transcript:Ghosts Ahoy"
    ]
    wiki = json.loads((config.DATA_PATH / "dialogues/wiki-pages.json").read_text())
    structure = bindings["Ghosts Ahoy"]["structure"]
    structured = update.apply_structure_annotations(
        "Ghosts Ahoy", quest["wikitext"], structure, quest["revision"]
    )
    raw = apply_capture_lines("Ghosts Ahoy", structured, sources["Ghosts Ahoy"], quest["revision"])
    assert raw == apply_capture_lines(
        "Ghosts Ahoy", structured, sources["Ghosts Ahoy"], quest["revision"]
    )
    # Robin's coin checks move up a level so they follow either opening (with or without the bow).
    assert all(fix["depth"] >= 1 for fix in structure["lines"])
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines(
            "Ghosts Ahoy", "\n" + structured, sources["Ghosts Ahoy"], quest["revision"]
        )
    with pytest.raises(ValueError, match="Stale dialogue capture source"):
        apply_capture_lines(
            "Ghosts Ahoy", structured, sources["Ghosts Ahoy"], quest["revision"] + 1
        )
    for name in ("Ghost guard", "Old crone"):
        page = wiki["Transcript:" + name]
        assert sources[name]["revision"] == page["revision"]
        apply_capture_lines(name, page["wikitext"], sources[name], page["revision"])

    exported = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    variants = exported["Ghosts Ahoy"]["variants"]
    # Velorina's vision (capture tick 265) and her completion line (1968).
    vision = json.dumps(variants["returning-to-velorina-after-talking-to-necrovarus"])
    assert "that there looms castles to the west" in vision
    assert "[player name]- I sensed" in variants["talking-to-velorina-2"][0]["text"]
    # The crone's first materials speech asks for the translation before her menu (452-453).
    milky = next(
        step for step in variants["talking-to-the-old-crone"] if step.get("id") == "pnTKEw"
    )["steps"]
    menu = next(index for index, step in enumerate(milky) if step.get("type") == "choice")
    assert milky[menu - 1]["text"].startswith("I cannot read the strange letters")
    # Robin with the bow asks for the autograph first (1227-1230); the coin checks follow either way.
    robin = variants["something-to-translate-the-book-of-haricanto-talking-to-robin"]
    assert robin[0]["text"] == "If the player has an oak longbow in their inventory:"
    assert robin[0]["steps"][0]["player"] == "Would you sign this oak longbow for me?"
    assert [step.get("text") for step in robin[2:4]] == [
        "If the player does not have 25 coins:",
        "If the player has at least 25 coins:",
    ]
    loses = next(
        step
        for step in robin[3]["steps"][0]["options"][0]["steps"]
        if step.get("text") == "If the player loses:"
    )["steps"]
    owed_nothing = loses[1]
    assert owed_nothing["text"] == "If Robin does not owe the player any coins:"
    assert owed_nothing["steps"][0]["player"] == "Well done, you beat me."
    assert [option["text"] for option in owed_nothing["steps"][2]["options"]][-1] == (
        "No, that doesn't sound fun."
    )
    # A villager's refusal (1538).
    villager = json.dumps(variants["robes-of-necrovarus-talking-to-the-ghost-villagers"])
    assert "My answer is no." in villager
    # Without 2 Ectotokens the guard offers only the two captured options (106-108).
    guard = exported["Ghost guard"]["variants"]["standard-dialogue-before-or-during-ghosts-ahoy"]
    options = guard[0]["steps"][1]["options"]
    poor = [o["text"] for o in options if o.get("condition") != "If the player has at least 2 Ectotokens:"]
    assert poor == ["I don't have that many Ectotokens.", "Where can I get Ectotokens?"]
    # The farmers' thanks names Malcolm (349).
    crone = json.dumps(exported["Old crone"]["variants"])
    assert "Alice and Malcolm can communicate again." in crone
    assert "Alice and her husband" not in crone
