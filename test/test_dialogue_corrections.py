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
