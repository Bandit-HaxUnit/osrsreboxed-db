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
        for change in correction["changes"]:
            path = change["path"]
            try:
                parent = data
                for key in path[:-1]:
                    parent = parent[key]
                key = path[-1]
                exists = (
                    key in parent
                    if isinstance(parent, dict)
                    else 0 <= key < len(parent)
                )
                expected = fingerprint(parent[key]) if exists else None
            except (KeyError, IndexError, TypeError):
                raise ValueError(
                    f"Stale dialogue correction: {name} at {path}"
                ) from None
            if expected != change["expected"]:
                raise ValueError(f"Stale dialogue correction: {name} at {path}")
            targets.append((parent, key, change))
    for parent, key, change in targets:
        if "value" in change:
            parent[key] = copy.deepcopy(change["value"])
        else:
            del parent[key]
