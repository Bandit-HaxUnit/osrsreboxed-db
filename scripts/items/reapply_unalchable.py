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

import config
from builders.items.unalchable import WikiUnalchable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    with open(Path(config.DATA_ITEMS_PATH / "items-unalchable.json"), encoding="utf-8") as f:
        unalchable = json.load(f)
    with open(Path(config.DATA_ITEMS_PATH / "items-wiki-page-text.json"), encoding="utf-8") as f:
        page_text = json.load(f)
    rule = WikiUnalchable(unalchable, page_text)
    changed = 0
    for path in sorted(Path(config.DOCS_PATH / "items-json").glob("*.json")):
        raw = path.read_text(encoding="utf-8", newline="")
        item = json.loads(raw)
        if item.get("highalch") is None and item.get("lowalch") is None:
            continue
        if not rule(item.get("wiki_name"), item.get("wiki_url")):
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
