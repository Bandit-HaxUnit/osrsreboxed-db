"""Consumer entrypoints and effect parameters, without copied dialogue text."""

import copy

from scripts.dialogues.hooks import walk


def apply_bindings(data, bindings):
    for name, binding in bindings.items():
        record = data["records"][name]
        variants = record.get(
            "variants", {"standard-dialogue": record.get("steps", [])}
        )
        for npc_id, names in binding.get("npc_ids", {}).items():
            if not set(names) <= variants.keys():
                raise ValueError(f"Stale dialogue identity binding: {name}")
            data["index"].setdefault(npc_id, []).append(
                {"page": "Transcript:" + name, "variants": list(names)}
            )
        effects = binding.get("effects", {})
        seen = set()
        for steps in [*variants.values(), *record.get("branches", {}).values()]:
            for node in walk(steps):
                if node.get("id") in effects:
                    node.update(effects[node["id"]])
                    seen.add(node["id"])
        if seen != effects.keys():
            raise ValueError(f"Stale dialogue effect binding: {name}")
        for alias, anchor in binding.get("variants", {}).items():
            matches = []

            def find(steps, visiting):
                for index, node in enumerate(steps):
                    if node.get("id") == anchor["after"]:
                        matches.append(steps[index + 1 :])
                    find(node.get("steps", []), visiting)
                    for option in node.get("options", []):
                        find(option.get("steps", []), visiting)
                    if node.get("type") == "call" and node["branch"] not in visiting:
                        find(
                            record["branches"][node["branch"]],
                            visiting | {node["branch"]},
                        )

            find(variants[anchor["variant"]], set())
            if len(matches) != 1 or not matches[0]:
                raise ValueError(f"Stale dialogue resume binding: {name}.{alias}")
            suffix = matches[0]
            if anchor.get("skip_player"):
                while suffix and "player" in suffix[0]:
                    suffix = suffix[1:]
            if not suffix:
                raise ValueError(f"Empty dialogue resume binding: {name}.{alias}")
            if "steps" in record:
                record.pop("steps")
                record.update(default="standard-dialogue", variants=variants)
            variants[alias] = copy.deepcopy(suffix)
            page = "Transcript:" + name
            sections = data["authoring"][page]["sections"]
            sections[alias] = sections[anchor["variant"]] + [
                "Resume after " + anchor["after"]
            ]
            for entries in data["index"].values():
                for entry in entries:
                    if entry["page"] == page and anchor["variant"] in entry["variants"]:
                        entry["variants"].append(alias)
