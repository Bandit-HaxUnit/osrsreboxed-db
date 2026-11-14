"""Export every max hit an NPC's infobox lists, with its label, from the canonical monster builder.

The combat export keeps one ``max_hit`` integer per monster. Some monsters list one
per style or condition (Killerwatt: "8 (Ranged), 6 (Melee), 15 (Ranged/Melee; without
insulated boots)"), and consumers need each of them. Only NPCs whose infobox lists
more than one max hit are exported; the rest are fully described by ``max_hit``.
"""

import argparse
import json
from pathlib import Path

import config
from builders.monsters.builder import Builder


def build_max_hits(builder=None):
    builder = builder or Builder()
    result = {}
    for monster_id in sorted(builder._get_entity_id_list(), key=int):
        monster = builder._build_entity(monster_id)
        valid, _ = monster.preprocessing()
        if not valid:
            continue
        monster.populate_monster()
        entries = getattr(monster, "max_hits", None) or []
        if len(entries) < 2:
            continue
        row = monster.monster_dict
        result[str(row["id"])] = {"name": row["name"], "max_hits": entries}
    return {"schema_version": 1, "npcs": result}


def export_max_hits(output):
    data = build_max_hits()
    with Path(output).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return len(data["npcs"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=config.DOCS_PATH / "npc-max-hits.json"
    )
    args = parser.parse_args()
    print(f"Exported {export_max_hits(args.output)} NPC max hit lists.")
