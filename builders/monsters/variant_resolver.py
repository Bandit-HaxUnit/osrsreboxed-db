"""Resolve which Infobox Monster variant an NPC id belongs to.

Many OSRS Wiki monster pages hold several variants (levels, forms, modes) in one or more
``{{Infobox Monster}}`` templates, numbered ``version1``, ``combat1``, ``hitpoints1`` and so
on. An NPC id is listed against one of them through the numbered ``id1``, ``id2`` keys.

The id index in ``scripts/wiki/wikitext_parser.py`` keeps one occurrence per id (the last page
that mentions it), and the name lookup always reads the first infobox. When neither answered
for a variant, the builder used to take variant 1, so an NPC could inherit another level's
stats. This module finds every variant that lists the id, and when that is ambiguous it checks
each candidate against the game cache, which the builder already treats as ground truth
(combat level, hitpoints and levels).

Cache stats are read from ``monsters-cache-data.json``. Its ``stats`` list is RuneLite's
``NpcComposition`` order, ``[attack, defence, strength, hitpoints, ranged, magic]``.
"""

import mwparserfromhell
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Order of the stat tuples below. Wiki keys: combat, hitpoints, att, def, str, range, mage.
STAT_NAMES = ("combat", "hitpoints", "att", "def", "str", "range", "mage")
_TRAILING_NUMBER = re.compile(r"^(.*?)\s*(\d+)$")


@dataclass(frozen=True)
class Variant:
    """One variant of an Infobox Monster page.

    ``version_number`` is "" for an unversioned infobox, otherwise the numbered suffix
    (``"1"``, ``"2"``...) the builder reads its numbered keys with.
    """

    page_name: str
    block_index: int
    version_number: str
    version_name: Optional[str]
    stats: Tuple[Optional[float], ...]
    ids: Tuple[int, ...]
    template: object = field(compare=False, repr=False, default=None)


def _as_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = re.sub(r"<!--.*?-->|<[^>]+>", "", value, flags=re.S)
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def _as_ids(value: Optional[str]) -> Tuple[int, ...]:
    if value is None:
        return ()
    text = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    found = set()
    for low, high in re.findall(r"(\d+)\s*-\s*(\d+)", text):
        if int(high) - int(low) < 200:
            found.update(range(int(low), int(high) + 1))
    found.update(int(number) for number in re.findall(r"\d+", text))
    return tuple(sorted(found))


def _normal_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.replace("_", " ")).strip().lower()


def cache_stats(cache_entry: dict) -> Tuple[Optional[float], ...]:
    """The cache's NPC stats in ``STAT_NAMES`` order, or Nones where the cache has no value."""
    stats = cache_entry.get("stats") or []
    combat = cache_entry.get("combatLevel")
    combat = float(combat) if combat is not None and combat >= 0 else None
    if len(stats) < 6:
        return (combat, None, None, None, None, None, None)
    return (
        combat,
        float(stats[3]),
        float(stats[0]),
        float(stats[1]),
        float(stats[2]),
        float(stats[4]),
        float(stats[5]),
    )


def page_variants(page_name: str, wikitext: str) -> List[Variant]:
    """Every variant of every Infobox Monster template on one wiki page."""
    code = mwparserfromhell.parse(wikitext)
    templates = [
        template
        for template in code.filter_templates()
        if "infobox monster" in str(template.name).strip().lower()
    ]
    variants = []
    for block_index, template in enumerate(templates, start=1):
        params = {
            str(param.name).strip().lower(): str(param.value).strip()
            for param in template.params
        }
        numbers = set()
        for key in params:
            match = _TRAILING_NUMBER.match(key)
            if match:
                numbers.add(int(match.group(2)))
        if not numbers:
            variants.append(
                Variant(
                    page_name=page_name,
                    block_index=block_index,
                    version_number="",
                    version_name=params.get("version"),
                    stats=tuple(_as_number(params.get(name)) for name in STAT_NAMES),
                    ids=_as_ids(params.get("id")),
                    template=template,
                )
            )
            continue
        for number in sorted(numbers):
            stats = []
            for name in STAT_NAMES:
                value = params.get(f"{name}{number}", params.get(name))
                stats.append(_as_number(value))
            ids_value = params.get(f"id{number}", params.get("id"))
            variants.append(
                Variant(
                    page_name=page_name,
                    block_index=block_index,
                    version_number=str(number),
                    version_name=params.get(f"version{number}"),
                    stats=tuple(stats),
                    ids=_as_ids(ids_value),
                    template=template,
                )
            )
    return variants


def build_index(all_wikitext_raw: Dict[str, str]) -> Dict[int, List[Variant]]:
    """Map every NPC id listed in any Infobox Monster to the variants that list it."""
    index: Dict[int, List[Variant]] = {}
    for page_name, wikitext in all_wikitext_raw.items():
        if not isinstance(wikitext, str) or "infobox monster" not in wikitext.lower():
            continue
        for variant in page_variants(page_name, wikitext):
            for npc_id in variant.ids:
                index.setdefault(npc_id, []).append(variant)
    return index


def stats_match(wiki_stats, game_stats) -> bool:
    """True when the wiki variant has combat level and hitpoints, and every level it gives agrees."""
    if wiki_stats[0] is None or wiki_stats[1] is None:
        return False
    if game_stats[0] is None or game_stats[1] is None:
        return False
    for wiki_value, game_value in zip(wiki_stats, game_stats):
        if (
            wiki_value is not None
            and game_value is not None
            and wiki_value != game_value
        ):
            return False
    return True


def resolve(
    npc_id: int,
    npc_name: str,
    game_stats: Tuple[Optional[float], ...],
    index: Dict[int, List[Variant]],
    raw_pages: Dict[str, str],
    previous: Optional[Tuple[str, str]] = None,
) -> Tuple[Optional[Variant], str]:
    """Pick the wiki variant for one NPC id, or return None with the reason it could not.

    ``previous`` is the (page name, version number) the builder would have used without the
    resolver. It only breaks ties between variants with identical stats.

    1. One variant lists the id: use it if its page is named after the NPC or its stats match
       the cache. Otherwise return None, so the previous choice stands.
    2. Several variants list the id: keep those whose stats match the cache; if that leaves
       one, use it. If it leaves several, keep the one on the page named after the NPC.
       With no stats match, use the one on the page named after the NPC if there is exactly one.
    3. No variant lists the id: use the page named after the NPC, and only a variant whose
       stats match the cache, and only if that is unique.
    """
    occurrences = index.get(npc_id, [])
    if len(occurrences) == 1:
        only = occurrences[0]
        if _normal_title(only.page_name) == _normal_title(npc_name) or stats_match(
            only.stats, game_stats
        ):
            return only, "one infobox lists this id"
        return None, (
            f"one infobox lists this id, on page {only.page_name!r} which is not named after "
            "the NPC, and its stats do not match the cache"
        )

    if occurrences:
        pool = occurrences
        origin = "several infoboxes list this id"
    else:
        wikitext = raw_pages.get(npc_name)
        if not isinstance(wikitext, str):
            return None, "no wiki page is named after the cache name"
        pool = page_variants(npc_name, wikitext)
        origin = "no infobox lists this id; page named after the cache name"

    matches = [variant for variant in pool if stats_match(variant.stats, game_stats)]
    named = [
        variant
        for variant in pool
        if _normal_title(variant.page_name) == _normal_title(npc_name)
    ]

    if len(matches) == 1:
        return matches[0], f"{origin}; cache stats match"
    if len(matches) > 1:
        narrowed = [variant for variant in matches if variant in named]
        if len(narrowed) == 1:
            return narrowed[0], f"{origin}; cache stats match and page name matches"
        if all(variant.stats == matches[0].stats for variant in matches):
            # Identical stats across variants (e.g. "Level 24, 1" to "Level 24, 9"): the cache
            # pins the stats, not the variant name. Keep the previous choice when it is one of
            # them, otherwise the first is used. Either way the name is ambiguous.
            kept = [
                variant
                for variant in matches
                if previous is not None
                and (variant.page_name, variant.version_number) == previous
            ]
            if len(kept) == 1:
                return kept[0], (
                    f"ambiguous: {origin}; {len(matches)} variants share the cache stats, "
                    "the previous choice is kept"
                )
            return matches[0], (
                f"ambiguous: {origin}; {len(matches)} variants share the cache stats, "
                "the first one is used"
            )
        return None, f"{origin}; several variants match the cache stats"
    if occurrences and len(named) == 1:
        return named[0], f"{origin}; no stats match, page name matches"
    return None, f"{origin}; no variant matches the cache stats"
