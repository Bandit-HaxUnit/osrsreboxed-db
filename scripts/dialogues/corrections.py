"""Retain reviewed runtime fixes without changing the cached wiki revisions."""

import copy
import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def apply_corrections(data, corrections):
    # Check every source before mutating anything or publishing an export.
    for name, correction in corrections.items():
        current = (
            fingerprint(data["records"][name]) if name in data["records"] else None
        )
        if current != correction["base_sha256"]:
            raise ValueError(
                f"Stale dialogue correction: {name}; review the source changes"
            )
    targets = []
    for name, correction in corrections.items():
        for position, change in enumerate(correction["changes"]):
            path = change["path"]
            try:
                parent = data
                for key in path[:-1]:
                    parent = parent[key]
                key = path[-1]
                if isinstance(parent, list):
                    # Indices name the record before any change; a negative one would count from the end.
                    if type(key) is not int or key < 0:
                        raise TypeError
                    exists = key < len(parent)
                else:
                    exists = key in parent
                expected = fingerprint(parent[key]) if exists else None
            except (KeyError, IndexError, TypeError):
                raise ValueError(
                    f"Stale dialogue correction: {name} at {path}"
                ) from None
            if expected != change["expected"]:
                raise ValueError(f"Stale dialogue correction: {name} at {path}")
            if "insert" in change and (
                "value" in change or not isinstance(parent, list) or key > len(parent)
            ):
                raise ValueError(f"Stale dialogue correction: {name} at {path}")
            # A list edit or any delete must name a node that is there.
            if (
                "insert" not in change
                and not exists
                and (isinstance(parent, list) or "value" not in change)
            ):
                raise ValueError(f"Stale dialogue correction: {name} at {path}")
            targets.append((parent, key, change, name, position))
    # Every path was checked against the record as it was. Apply each list's changes from its
    # highest index down, so an insert or delete never shifts a node another change still names.
    # At one index the node's own edit goes before the inserts, and inserts keep their listed order.
    claimed = set()
    for parent, key, change, name, _ in targets:
        if "insert" in change:
            continue
        if (id(parent), key) in claimed:
            raise ValueError(
                f"Conflicting dialogue correction: {name} at {change['path']}"
            )
        claimed.add((id(parent), key))
    # A change inside a node that another change replaces or deletes would edit a detached copy.
    replaced = [
        (name, tuple(change["path"]))
        for _, _, change, name, _ in targets
        if "insert" not in change
    ]
    for _, _, change, name, _ in targets:
        path = tuple(change["path"])
        if any(
            owner == name and len(r) < len(path) and path[: len(r)] == r
            for owner, r in replaced
        ):
            raise ValueError(
                f"Conflicting dialogue correction: {name} at {change['path']}"
            )

    def order(target):
        parent, key, change, _, position = target
        if not isinstance(parent, list):
            return (0, 0, 0, position)
        return (
            1,
            -key,
            1 if "insert" in change else 0,
            -position if "insert" in change else 0,
        )

    for parent, key, change, _, _ in sorted(targets, key=order):
        if "insert" in change:
            # `expected` anchors the node now at the index (null at the end); it moves down.
            parent.insert(key, copy.deepcopy(change["insert"]))
        elif "value" in change:
            parent[key] = copy.deepcopy(change["value"])
        else:
            del parent[key]
