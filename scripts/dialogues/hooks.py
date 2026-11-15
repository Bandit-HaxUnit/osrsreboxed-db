"""Source-addressed dialogue nodes and explicit plugin handoff points.

No quest state is inferred or executed here. The consumer binds condition keys
and quest events; unresolved references remain blocking nodes.
"""

import collections
import hashlib
import json
import re

import mwparserfromhell as mw

from scripts.shops.shop_owners import npc_ids_from_wikitext
from scripts.dialogues.flow import resolve_navigation, resolve_shared
from scripts.dialogues.fetch import transcript_identity


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def token(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def walk(nodes, branches=None, seen=None):
    seen = set() if seen is None else seen
    for node in nodes:
        yield node
        yield from walk(node.get("steps", []), branches, seen)
        yield from walk(node.get("options", []), branches, seen)
        if branches and node.get("type") == "call" and node["branch"] not in seen:
            seen.add(node["branch"])
            yield from walk(branches[node["branch"]], branches, seen)


def identity(name, page, clean):
    raw = page.get("wikitext", "")
    ids = npc_ids_from_wikitext(raw) if raw else []
    names = {name}
    for template in mw.parse(raw).filter_templates():
        if str(template.name).strip().casefold() not in (
            "infobox npc",
            "infobox monster",
            "infobox pet",
        ):
            continue
        for param in template.params:
            if re.fullmatch(r"name\d*", str(param.name).strip(), re.I):
                names.add(clean(param.value))
    return ids, names


def _base_name(text):
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip().casefold()


def _words(text):
    return re.findall(r"[a-z0-9']+", text.casefold())


def _is_subsequence(needle, haystack):
    remaining = iter(haystack)
    return all(word in remaining for word in needle)


def speaker_ids(speaker, participants, identities):
    """NPC ids for a spoken label, read only from the page's own participants.

    Transcripts label a speaker with a short name ("Hrafn", "King Sorvott IV",
    "Guard") while the Transcript list names the NPC page ("HRH Hrafn", "King
    Gjuki Sorvott IV", "Guard (Jatizso)"). The strictest rule that finds exactly
    one participant wins: a full name or infobox name, then the page title
    without its disambiguation, then the label's words in order within a
    participant's name. A tie at any rule resolves nothing, and no rule looks
    outside the participant list, so NPCs sharing a short name are never merged.
    """
    label = speaker.strip()
    if not label or "/" in label or label.casefold() == "player":
        return []
    folded = label.casefold()
    wanted = _words(label)
    rules = (
        lambda page, names: folded in {n.casefold() for n in names},
        lambda page, names: folded == _base_name(page)
        or folded in {_base_name(n) for n in names},
        lambda page, names: bool(wanted)
        and _is_subsequence(wanted, _words(_base_name(page))),
    )
    for rule in rules:
        found = [
            page
            for page in participants
            if rule(page, identities.get(page, ([], {page}))[1] | {page})
        ]
        if len(found) == 1:
            return sorted(set(identities.get(found[0], ([], set()))[0]))
        if found:
            return []
    return []


def annotate_speaker_ids(record, participants, identities):
    """Add `speaker_ids` to lines spoken by a listed participant.

    Runs on the exported record after corrections: their fingerprints cover the
    record as compacted, so the field must not exist before they are checked.
    Node ids are untouched.
    """
    if not participants:
        return
    steps_lists = (
        [record["steps"]]
        if "steps" in record
        else list(record.get("variants", {}).values())
    )
    steps_lists += list(record.get("branches", {}).values())
    cache = {}
    for steps in steps_lists:
        for node in walk(steps):
            speaker = node.get("speaker")
            if node.get("type") != "line" or not speaker:
                continue
            if speaker not in cache:
                cache[speaker] = speaker_ids(speaker, participants, identities)
            if cache[speaker]:
                node["speaker_ids"] = list(cache[speaker])


def npc_identities(npc_pages, clean):
    """NPC page title -> (infobox ids, names the wiki calls that NPC)."""
    return {name: identity(name, page, clean) for name, page in npc_pages.items()}


def annotate(nodes, parent, quest_names):
    counts = collections.Counter()
    for node in nodes:
        # Exclude child bodies: adding a line to an option does not rename its
        # branch or descendants. Duplicate identical siblings use a local suffix.
        own = {
            k: v
            for k, v in node.items()
            if k not in ("steps", "options", "presentation") and not k.startswith("_")
        }
        own = node.pop("_identity", own)
        key = token([parent, own])
        counts[key] += 1
        node["id"] = f"{parent.split('/node:')[0]}/node:{key}" + (
            f"-{counts[key]}" if counts[key] > 1 else ""
        )
        condition = node.get("condition") or (
            node.get("text") if node.get("type") == "condition" else None
        )
        if condition:
            node["condition_key"] = f"condition:{token([parent, condition])}"
        if node.get("type") == "action":
            start = re.fullmatch(r"(.+?) is started\.?", node.get("text", ""), re.I)
            if start and slug(start[1]) in quest_names:
                node.update(
                    action="quest_start",
                    quest=quest_names[slug(start[1])],
                    hook=f"quest:{slug(start[1])}:start",
                    action_source="text",
                )
        annotate(node.get("steps", []), node["id"], quest_names)
        annotate(node.get("options", []), node["id"], quest_names)
        prompt = re.fullmatch(r"Start (.+?)\?", node.get("prompt", ""), re.I)
        if prompt:
            # Try the literal title first: Quest and The can be part of a name.
            title = prompt[1]
            candidates = [title, re.sub(r"^the\s+", "", title, flags=re.I)]
            candidates += [
                re.sub(r"\s+quest$", "", value, flags=re.I) for value in candidates
            ]
            key = next(
                (slug(value) for value in candidates if slug(value) in quest_names),
                None,
            )
            if key:
                for option in node.get("options", []):
                    if option.get("text", "").strip().casefold().rstrip(".! ") == "yes":
                        option["hook"] = f"quest:{key}:start"
                        option["quest"] = quest_names[key]


def enrich_records(
    npcs, quests, npc_pages, clean, bindings=None, transcript_pages=None
):
    identities = npc_identities(npc_pages, clean)
    all_records = {
        "Transcript:" + name: record
        for group in (npcs, quests)
        for name, record in group.items()
    }
    quest_names = {
        slug(name): name
        for name, record in quests.items()
        if record.get("activation") != "explicit"
    }
    index = collections.defaultdict(list)
    for page, record in all_records.items():
        name = page.removeprefix("Transcript:")
        is_npc = name in npcs
        ids, names = identities.get(name, ([], {name})) if is_npc else ([], set())
        if is_npc and transcript_pages is not None:
            raw = transcript_pages.get(page, {}).get("wikitext", "")
            target = transcript_identity(raw, name, npc_pages)
            if target != name:
                source = npc_pages.get(target)
                if not source or source.get("missing"):
                    raise ValueError(
                        f"Missing transcript identity page: {name} -> {target}"
                    )
                ids, names = identity(name, source, clean)
        if is_npc:
            record["npc_ids"] = ids
        for variant, steps in record["variants"].items():
            for node in walk(steps):
                if node.get("type") == "line" and node.get("speaker") in names:
                    text = node.pop("text")
                    node.pop("type")
                    node.pop("speaker")
                    node["npc"] = text
            annotate(steps, f"{page}#{variant}", quest_names)
            for node in walk(steps):
                if node.get("type") == "reference" and not node.get("target"):
                    node["target"] = page
    resolve_shared(npcs, quests, identities, bindings)
    for page, record in all_records.items():
        binding = (bindings or {}).get(page.removeprefix("Transcript:"), {})
        resolve_navigation(record, binding.get("navigation"))
    for page, record in all_records.items():
        name = page.removeprefix("Transcript:")
        is_npc = name in npcs
        ids = record.get("npc_ids", [])
        if is_npc:
            for npc_id in ids:
                index[str(npc_id)].append(
                    {"page": page, "variants": list(record["variants"])}
                )
        else:
            # Participants come from explicit Transcript list wiki-page links,
            # never a global short-name match (multiple NPCs can be called Cook).
            for participant in record.get("participants", []):
                participant_ids, aliases = identities.get(participant, ([], set()))
                variants = [
                    key
                    for key, steps in record["variants"].items()
                    if any(
                        n.get("speaker") in aliases
                        for n in walk(steps, record.get("branches"))
                    )
                ]
                if variants:
                    for npc_id in participant_ids:
                        index[str(npc_id)].append({"page": page, "variants": variants})
    for record in all_records.values():
        for steps in [
            *record["variants"].values(),
            *record.get("branches", {}).values(),
        ]:
            for node in walk(steps):
                if node.get("type") != "reference":
                    continue
                if not node["target"]:
                    node["target"] = record["source"]["page"]
                target = all_records.get(node["target"])
                section = node.get("section", "")
                matches = (
                    []
                    if target is None
                    else [
                        key
                        for key, section_path in target["sections"].items()
                        if slug(section) in (key, slug(section_path[-1]))
                    ]
                )
                if section and len(matches) == 1:
                    node["variant"] = matches[0]
                # A page-only reference is NOT a license to replay its opening.
                node["resolved"] = "variant" in node
                node["page_available"] = target is not None
    return dict(sorted(index.items(), key=lambda item: int(item[0])))
