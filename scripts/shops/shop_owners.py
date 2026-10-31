"""
Author:  Toby Wisener
Email:   tobywisener@googlemail.com

Description:
Script to resolve the NPC that runs each OSRS Wiki shop.

Shop pages name their shopkeeper in the ``{{Infobox Shop}}`` ``owner`` field,
as a link to the NPC's own wiki page. Matching that name against the NPC
database is not enough on its own — "Shop keeper" is 12 different NPC IDs — so
this module fetches each owner's wiki page and reads the NPC IDs straight out
of its infobox, which is disambiguated per location.

Produces ``data/shops/shop-owners.json``, which ``shops_items.process`` merges
into the exported shop data.

Copyright (c) 2026, Toby Wisener

###############################################################################
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
###############################################################################
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Set

import requests

import config
from builders.run_log import begin_run
from scripts.wiki.wiki_page_text import WikiPageText
from scripts.wiki.wikitext_parser import WikitextTemplateParser

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

OSRS_WIKI_API_URL = "https://oldschool.runescape.wiki/api.php"

SHOPS_TEXT_FP = Path(config.DATA_SHOPS_PATH / "shops-wiki-page-text.json")
OWNERS_TEXT_FP = Path(config.DATA_SHOPS_PATH / "shop-owners-wiki-page-text.json")
OWNERS_FP = Path(config.DATA_SHOPS_PATH / "shop-owners.json")

# The owner field of an {{Infobox Shop}} template. Versioned infoboxes use
# owner1, owner2, ... (one per shop version), so read every field, not just `owner`.
OWNER_FIELD = re.compile(r"\|\s*owner\d*\s*=\s*(.+)", re.I)
# Wiki links, keeping the page title and the display text separately.
WIKI_LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
# Infoboxes that carry NPC identities.
NPC_INFOBOXES = ["infobox npc", "infobox monster"]
# Values meaning "this shop has no shopkeeper" (chest and interface shops).
NO_OWNER_VALUES = {"none", "no", "n/a", "na", "-", "unknown"}

# Click options that open a shop. Most shopkeepers use "Trade", but the cache
# carries a whole Trade-* family ("Trade-Co-op", "Trade-General-Store"), and
# reward shops use their own wording.
SHOP_OPTION_TEXTS = {
    "trade",
    "exchange",
    "shop",
    "store",
    "buy",
    "buy-items",
    "rewards",
    "get-rewards",
    "claim",
    "collect",
}
SHOP_OPTION_PREFIXES = ("trade-", "trade ")


def parse_shop_owners(wikitext: str) -> List[Dict]:
    """Read the shopkeepers named by a shop page's infobox.

    Versioned infoboxes name one owner per version (``owner1``, ``owner2``, …),
    so every field is read and duplicates are dropped.

    :param wikitext: The wikitext content of the shop page.
    :return: List of owners, each with a wiki page and display name.
    """
    owners: List[Dict] = []
    seen = set()
    for match in OWNER_FIELD.finditer(wikitext):
        value = match.group(1).strip()
        named = [
            {"name": (display or page).strip(), "wiki_page": page.strip()}
            for page, display in WIKI_LINK.findall(value)
            if page.strip()
        ]
        if not named:
            # A handful of shops name an owner without linking to a page.
            plain = re.sub(r"\[\[|\]\]|'{2,}", "", value).strip()
            if (
                plain
                and not plain.startswith("{{")
                and plain.lower() not in NO_OWNER_VALUES
            ):
                named = [{"name": plain, "wiki_page": None}]
        for owner in named:
            key = (owner["wiki_page"], owner["name"])
            if key not in seen:
                seen.add(key)
                owners.append(owner)
    return owners


def _owners_by_shop() -> Dict[str, List[Dict]]:
    """Map every shop page title to the owners named on it."""
    if not SHOPS_TEXT_FP.exists():
        logger.error(
            "shops-wiki-page-text.json not found. Run shops_properties.py first."
        )
        return {}

    with open(SHOPS_TEXT_FP) as shops_file:
        all_wikitext = json.load(shops_file)

    owners_by_shop = {}
    for page_title, wikitext in all_wikitext.items():
        if not isinstance(wikitext, str):
            continue
        owners = parse_shop_owners(wikitext)
        if owners:
            owners_by_shop[page_title] = owners
    return owners_by_shop


# NPC pages whose infobox links a shop with `|shop = [[...]]` (or shop1, ...).
# A shop page's owner field often names only the keeper, while the assistants'
# own pages say which shop they run, so both sides are read.
SHOP_LINK_SEARCH = r'hastemplate:"Infobox NPC" insource:/shop[0-9]* *= *\[\[/'


def shop_linking_npc_pages() -> List[str]:
    """List the wiki NPC pages whose infobox has a ``shop`` link.

    :return: Sorted page titles, from the wiki search API.
    """
    titles = set()
    offset = 0
    while offset is not None:
        response = requests.get(
            OSRS_WIKI_API_URL,
            headers=config.custom_agent,
            params={
                "action": "query",
                "list": "search",
                "srsearch": SHOP_LINK_SEARCH,
                "srnamespace": 0,
                "srlimit": 500,
                "sroffset": offset,
                "srprop": "",
                "format": "json",
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        titles.update(hit["title"] for hit in data["query"]["search"])
        offset = data.get("continue", {}).get("sroffset")
    return sorted(titles)


def fetch() -> None:
    """Fetch the wiki page text of every shop owner.

    Owners are the pages a shop names, and the NPC pages that name a shop in
    their own infobox. Pages already fetched are skipped, so an interrupted run
    can be resumed and a repeat run costs nothing.
    """
    owners_by_shop = _owners_by_shop()
    if not owners_by_shop:
        return

    wanted = sorted(
        {
            owner["wiki_page"]
            for owners in owners_by_shop.values()
            for owner in owners
            if owner["wiki_page"]
        }
        | set(shop_linking_npc_pages())
    )

    cached = {}
    if OWNERS_TEXT_FP.exists():
        with open(OWNERS_TEXT_FP) as owners_file:
            cached = json.load(owners_file)

    missing = [page for page in wanted if page not in cached]
    logger.info(
        f"Shop owner pages: {len(wanted)} total, {len(wanted) - len(missing)} cached, "
        f"{len(missing)} to fetch..."
    )

    for count, page_title in enumerate(missing, start=1):
        if count % 50 == 0:
            logger.info(f"Progress: {count:4d} of {len(missing):4d} owner pages")
        page = WikiPageText(OSRS_WIKI_API_URL, page_title)
        page.extract_page_wiki_text()
        page.export_wiki_text_to_json(str(OWNERS_TEXT_FP))

    logger.info("Fetched shop owner page text.")


def npc_ids_from_wikitext(wikitext: str) -> List[int]:
    """Read every recognized NPC/Monster identity from a page.

    A page can contain several infobox types and repeated instances, including
    nested Switch variants. Each occurrence contributes its non-versioned and
    versioned ``id`` fields; unrelated infobox types are ignored.

    :param wikitext: The wikitext content of the NPC page.
    :return: Sorted list of NPC IDs, empty when the page has no recognized infobox.
    """
    npc_ids = set()
    for infobox in NPC_INFOBOXES:
        version = 1
        while True:
            parser = WikitextTemplateParser(wikitext)
            if not parser.extract_infobox(infobox, version):
                break
            parser.determine_infobox_versions()
            for npc_id in parser.extract_infobox_ids():
                try:
                    npc_ids.add(int(str(npc_id).strip()))
                except (TypeError, ValueError):
                    continue
            version += 1
    return sorted(npc_ids)


def npc_shops_from_wikitext(wikitext: str) -> Dict[str, Set[int]]:
    """Read which shops an NPC page says its NPCs run.

    Each NPC/Monster infobox's ``shop`` field links the shop pages; a versioned
    infobox can give ``shop1``, ``shop2``, ... per version, in which case only
    that version's IDs run the linked shop. Unversioned IDs fall back to the
    plain ``shop`` field.

    :param wikitext: The NPC page's wikitext.
    :return: Mapping of linked shop page title to the NPC IDs that run it.
    """
    shops: Dict[str, Set[int]] = {}
    for infobox in NPC_INFOBOXES:
        version = 1
        while True:
            parser = WikitextTemplateParser(wikitext)
            if not parser.extract_infobox(infobox, version):
                break
            parser.determine_infobox_versions()
            for npc_id, npc_version in parser.extract_infobox_ids().items():
                value = (
                    parser.extract_infobox_value(f"shop{npc_version}")
                    if npc_version
                    else None
                ) or parser.extract_infobox_value("shop")
                for page, _ in WIKI_LINK.findall(value or ""):
                    title = page.partition("#")[0].strip().replace("_", " ")
                    if title:
                        title = title[0].upper() + title[1:]
                        shops.setdefault(title, set()).add(npc_id)
            version += 1
    return shops


def _shop_title(link: str, shop_titles: Set[str]):
    """Match a ``shop =`` link to a shop page title, or None.

    Shop page titles often end in a full stop the links leave out
    ("Varrock General Store" vs "Thessalia's Fine Clothes.").
    """
    for title in (link, f"{link}.", link.rstrip(".")):
        if title in shop_titles:
            return title
    return None


def _infobox_name(wikitext: str, fallback: str) -> str:
    parser = WikitextTemplateParser(wikitext)
    if parser.extract_infobox("infobox npc"):
        name = parser.extract_infobox_value("name")
        if name and "{{" not in name and "[[" not in name:
            return name
    return re.sub(r"\s*\([^()]*\)$", "", fallback)


def process() -> None:
    """Resolve every shop owner to NPC IDs and export the mapping."""
    owners_by_shop = _owners_by_shop()
    if not owners_by_shop:
        return

    cached = {}
    if OWNERS_TEXT_FP.exists():
        with open(OWNERS_TEXT_FP) as owners_file:
            cached = json.load(owners_file)

    # One page can own several shops, so resolve each page a single time.
    ids_by_page: Dict[str, List[int]] = {}
    for page_title, wikitext in cached.items():
        if isinstance(wikitext, str) and wikitext != "None":
            ids_by_page[page_title] = npc_ids_from_wikitext(wikitext)

    export = {}
    resolved = 0
    for shop_name, owners in owners_by_shop.items():
        shop_owners = []
        for owner in owners:
            npc_ids = (
                ids_by_page.get(owner["wiki_page"], []) if owner["wiki_page"] else []
            )
            shop_owners.append(
                {
                    "name": owner["name"],
                    "wiki_page": owner["wiki_page"],
                    "npc_ids": npc_ids,
                }
            )
        export[shop_name] = shop_owners

    # Owners named only on their own NPC page: the page's infobox links the shop.
    with open(SHOPS_TEXT_FP) as shops_file:
        shop_titles = set(json.load(shops_file))
    for page_title in sorted(cached):
        wikitext = cached[page_title]
        if not isinstance(wikitext, str) or wikitext == "None":
            continue
        for link, npc_ids in sorted(npc_shops_from_wikitext(wikitext).items()):
            shop_name = _shop_title(link, shop_titles)
            if shop_name is None:
                continue
            owners = export.setdefault(shop_name, [])
            if any(owner["wiki_page"] == page_title for owner in owners):
                continue
            owners.append(
                {
                    "name": _infobox_name(wikitext, page_title),
                    "wiki_page": page_title,
                    "npc_ids": sorted(npc_ids),
                }
            )

    for shop_owners in export.values():
        if any(owner["npc_ids"] for owner in shop_owners):
            resolved += 1

    with open(OWNERS_FP, "w") as out_file:
        json.dump(export, out_file, indent=4)

    logger.info(
        f"Resolved shop owners: {resolved} of {len(export)} shops have NPC IDs."
    )


def is_shop_option(option_text: str) -> bool:
    """True when a click option opens a shop interface.

    :param option_text: The option text from the NPC's cache definition.
    :return: True when the option is a shop-opening one.
    """
    text = option_text.strip().lower()
    return text in SHOP_OPTION_TEXTS or text.startswith(SHOP_OPTION_PREFIXES)


def load_npc_options() -> Dict[str, Dict[str, str]]:
    """Load NPC click options, keyed by NPC ID as a string.

    :return: Mapping of NPC ID to its options, empty when the file is missing.
    """
    interactions_fp = Path(config.DOCS_PATH / "npcs-interactions.json")
    if not interactions_fp.exists():
        logger.warning(
            "npcs-interactions.json not found. Run scripts.npcs.update to "
            "resolve which click option opens each shop."
        )
        return {}
    with open(interactions_fp) as interactions_file:
        interactions = json.load(interactions_file)
    return {
        npc_id: npc.get("options", {})
        for npc_id, npc in interactions.get("npcs", {}).items()
    }


def shop_option_for(
    npc_id: int, npc_options: Dict[str, Dict[str, str]], shop_name: str = None
) -> Dict:
    """Find the click option that opens this NPC's shop.

    An NPC can run more than one shop (a Slayer master has Trade and Rewards),
    so when the shop name names one of the candidate options that one wins.

    A null option means one of two different things, so the result says which:

    ``click``
        The NPC has a shop-opening option; ``option_slot`` is the menu slot.
    ``dialogue``
        The NPC has click options but none open a shop, so the shop is reached
        by talking to them. Their left-click is almost always ``Talk-to``, which
        opens a conversation, not the shop.
    ``unknown``
        No click options are known for this NPC ID. Usually the wiki infobox
        names a variant of the NPC that has no options of its own — a cutscene
        or quest version — while the shopkeeper players meet is another ID.

    :param npc_id: The NPC ID to look up.
    :param npc_options: Mapping from :func:`load_npc_options`.
    :param shop_name: The shop page title, to pick between several options.
    :return: Dictionary with the option text, its 1-based slot, and the source.
    """
    options = npc_options.get(str(npc_id))
    if not options:
        return {"option": None, "option_slot": None, "option_source": "unknown"}
    candidates = [
        (int(slot), options[slot])
        for slot in sorted(options, key=int)
        if is_shop_option(options[slot])
    ]
    if candidates:
        if shop_name:
            needle = shop_name.casefold()
            for slot, text in candidates:
                if text.strip().casefold() in needle:
                    return {
                        "option": text,
                        "option_slot": slot,
                        "option_source": "click",
                    }
        slot, text = candidates[0]
        return {"option": text, "option_slot": slot, "option_source": "click"}
    return {"option": None, "option_slot": None, "option_source": "dialogue"}


def load() -> Dict[str, List[Dict]]:
    """Load the shop owner mapping, or an empty mapping when it is missing."""
    if not OWNERS_FP.exists():
        logger.warning("shop-owners.json not found. Run shop_owners.py first.")
        return {}
    with open(OWNERS_FP) as owners_file:
        return json.load(owners_file)


if __name__ == "__main__":
    begin_run("scripts_shops_shop_owners")
    fetch()
    process()
