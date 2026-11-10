import json

import config
from scripts.dialogues import update


def walk(steps, guarded=False):
    for node in steps:
        inner = guarded or node.get("type") == "condition" or "condition" in node
        yield node, guarded
        yield from walk(node.get("steps", []), inner)
        for option in node.get("options", []):
            yield from walk(option.get("steps", []), inner or "condition" in option)


def warnings(record):
    for steps in record["variants"].values():
        if isinstance(steps, dict):
            steps = steps["steps"]
        for node, guarded in walk(steps):
            if str(node.get("text", "")).startswith("Before starting this quest"):
                yield node, guarded


def test_bare_recommended_level_warning_is_guarded():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "quest-pages.json").read_text()
    )["Transcript:Druidic Ritual"]
    parsed = update.parse_npc("Druidic Ritual", source["wikitext"])
    found = [
        node
        for variant in parsed["variants"].values()
        for node, _ in walk(variant["steps"])
        if node.get("type") == "condition"
        and node.get("text") == "If the player's combat level is lower than 10:"
    ]
    assert len(found) == 2
    for node in found:
        assert [step["type"] for step in node["steps"]] == ["message"]
        assert node["steps"][0]["text"].startswith("Before starting this quest")


def test_existing_conditions_are_not_wrapped_twice():
    source = json.loads(
        (config.DATA_PATH / "dialogues" / "quest-pages.json").read_text()
    )["Transcript:Elemental Workshop I"]
    parsed = update.parse_npc("Elemental Workshop I", source["wikitext"])
    assert warnings(parsed) and all(guarded for _, guarded in warnings(parsed))
    texts = [
        node["text"]
        for variant in parsed["variants"].values()
        for node, _ in walk(variant["steps"])
        if node.get("type") == "condition"
    ]
    assert "If the player's combat level is lower than 15:" in texts
    assert not any(text.startswith("If the player's combat level is lower than 15:") and texts.count(text) > 1 for text in texts)


def test_no_unguarded_recommended_level_warning_in_dump():
    records = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    bare = [
        name
        for name, record in records.items()
        if isinstance(record, dict) and "variants" in record
        for node, guarded in warnings(record)
        if not guarded
    ]
    assert bare == []
