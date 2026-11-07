import copy
import json

import pytest

import config
from scripts.dialogues.corrections import apply_corrections, fingerprint
from scripts.dialogues import update


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
