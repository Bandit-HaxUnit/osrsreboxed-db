import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]


def test_slayer_tasks_dump():
    dump = json.loads((ROOT / "docs/slayer-tasks.json").read_text())
    schema = json.loads((ROOT / "data/schemas/schema-slayer-tasks.json").read_text())
    dialogues = json.loads((ROOT / "docs/npc-dialogue-index.json").read_text())
    jsonschema.validate(dump, schema)
    assert len(dump) >= 10
    assert {entry["name"] for entry in dump.values()} >= {
        "Turael", "Spria", "Krystilia", "Konar quo Maten", "Mortimer"
    }
    assert all(entry["dialogue"] == entry["name"] for entry in dump.values())
    assert all(
        any(item["page"] == f"Transcript:{entry['dialogue']}" for item in dialogues[npc_id])
        for npc_id, entry in dump.items()
    )
    assert all(task["npc_names"] for entry in dump.values() for task in entry["tasks"])
    assert any("locations" in task for task in dump["8623"]["tasks"])


def test_fixed_amount_tasks_are_kept():
    # Konar assigns Ankou (50) and Nechryael (110) as a single amount, not a range.
    from scripts.slayer.update import number_range

    assert number_range("50") == [50, 50]
    assert number_range("120-170") == [120, 170]
    assert number_range("N/A") is None
    dump = json.loads((ROOT / "docs/slayer-tasks.json").read_text(encoding="utf-8"))
    konar = {task["slug"]: task for task in dump["8623"]["tasks"]}
    assert konar["ankou"]["quantity"] == [50, 50]
    assert konar["nechryael"]["quantity"] == [110, 110]
