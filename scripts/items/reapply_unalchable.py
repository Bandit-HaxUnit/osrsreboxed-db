"""
Re-apply the unalchable list to docs/items-json without a full item rebuild.

The item builder clears lowalch/highalch for items in data/items/items-unalchable.json
(builders/items/build_item.py). It used to match only the versioned wiki_name, so versioned
untradeables ("Dragon defender (Normal)") kept their alch values. This applies the corrected
rule (builders.items.unalchable) to the existing item files; afterwards run
`python -m scripts.update.update_json_files` to regenerate items-complete.json and
item-alch.json from them.

Usage: python -m scripts.items.reapply_unalchable
"""

import json
import logging
from pathlib import Path

import mwparserfromhell

import config
from builders.items.unalchable import infobox_alchable, is_unalchable, page_name_from_url, version_from_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def infobox(page_text):
    """The page's Infobox Item parameters as {name: value}, or {} when it has none."""
    if not isinstance(page_text, str):
        return {}
    for template in mwparserfromhell.parse(page_text).filter_templates():
        if str(template.name).strip().lower().startswith("infobox item"):
            return {str(param.name).strip(): str(param.value).strip() for param in template.params}
    return {}


def alchable_for(params, version):
    """The infobox's alchable answer for this version (alchableN, else alchable), or None."""
    if version:
        for key, value in params.items():
            if key.startswith("version") and key[7:].isdigit() and value == version:
                answer = infobox_alchable(params.get("alchable" + key[7:]))
                if answer is not None:
                    return answer
    return infobox_alchable(params.get("alchable"))


def main():
    with open(Path(config.DATA_ITEMS_PATH / "items-unalchable.json"), encoding="utf-8") as f:
        unalchable = json.load(f)
    with open(Path(config.DATA_ITEMS_PATH / "items-wiki-page-text.json"), encoding="utf-8") as f:
        page_text = json.load(f)
    infoboxes = {}
    changed = 0
    for path in sorted(Path(config.DOCS_PATH / "items-json").glob("*.json")):
        raw = path.read_text(encoding="utf-8", newline="")
        item = json.loads(raw)
        if item.get("highalch") is None and item.get("lowalch") is None:
            continue
        page = page_name_from_url(item.get("wiki_url"))
        if page not in infoboxes:
            infoboxes[page] = infobox(page_text.get(page))
        alchable = alchable_for(infoboxes[page], version_from_url(item.get("wiki_url")))
        if not is_unalchable(unalchable, item.get("wiki_name"), page, alchable=alchable):
            continue
        item["highalch"] = None
        item["lowalch"] = None
        newline = "\r\n" if "\r\n" in raw else "\n"
        text = json.dumps(item, indent=4)
        path.write_text(text.replace("\n", newline) + (newline if raw.endswith(("\n", "\r\n")) else ""), encoding="utf-8", newline="")
        changed += 1
    logger.info("Cleared alch values on %d items", changed)


if __name__ == "__main__":
    main()
