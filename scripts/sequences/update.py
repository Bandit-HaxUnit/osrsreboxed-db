"""
Description:
Program to generate the OSRS animation (sequence) name JSON dump.

The cache stores sequences by ID only; the game's own names for them ship in
RuneLite's generated gameval ``AnimationID.java``
(``public static final int HUMAN_SWORD_SLASH = 390;``). This reads that file at
a pinned RuneLite commit and writes sequence ID -> name to
``docs/sequence-names.json``, beside RuneLite's license
(``docs/sequence-names.LICENSE``). An ID with two names keeps the first.

The default commit is the gameval update for cache revision 241. Pass ``--ref``
for another revision's names, or ``--source`` to read a local copy.

Usage:
    python -m scripts.sequences.update
    python -m scripts.sequences.update --ref <runelite commit>
    python -m scripts.sequences.update --source /path/to/AnimationID.java

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

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

import requests

import config
from builders.run_log import begin_run

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# "Update GameVals to 2026-10-28-rev241"
RUNELITE_REF = "78c6083363c90b99d3cbe47f000245a25dd1039e"
RUNELITE_RAW = "https://raw.githubusercontent.com/runelite/runelite/{ref}/{path}"
ANIMATION_ID_PATH = (
    "runelite-api/src/main/java/net/runelite/api/gameval/AnimationID.java"
)

CONSTANT = re.compile(r"int\s+([A-Z0-9_]+)\s*=\s*(\d+)\s*;")


def fetch(ref: str, path: str) -> str:
    """A file from RuneLite's repository at ``ref``."""
    url = RUNELITE_RAW.format(ref=ref, path=path)
    response = requests.get(url, headers=config.custom_agent, timeout=60)
    response.raise_for_status()
    return response.text


def sequence_names(source: str) -> Dict[int, str]:
    """Sequence ID -> name, from the constants of ``AnimationID.java``."""
    names: Dict[int, str] = {}
    for line in source.splitlines():
        match = CONSTANT.search(line)
        if match:
            names.setdefault(int(match.group(2)), match.group(1))
    return dict(sorted(names.items()))


def write_dump(names: Dict[int, str], out_file: Path) -> None:
    """One sequence per line, so a renamed sequence shows as a one-line diff."""
    lines = [
        f"{json.dumps(str(seq_id))}:{json.dumps(name)}"
        for seq_id, name in names.items()
    ]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


def generate(
    out_file: Path,
    license_file: Path,
    ref: str = RUNELITE_REF,
    source_file: Optional[Path] = None,
) -> None:
    """Read ``AnimationID.java`` and write the name dump and its license."""
    if source_file is not None:
        source = source_file.read_text(encoding="utf-8")
    else:
        source = fetch(ref, ANIMATION_ID_PATH)
    names = sequence_names(source)
    if not names:
        raise SystemExit(">>> ERROR: no sequence names found in AnimationID.java")
    write_dump(names, out_file)
    license_text = fetch(ref, "LICENSE").replace("\r\n", "\n")
    license_file.write_text(license_text, encoding="utf-8")
    logger.info(
        "Wrote %d sequence names to %s (RuneLite %s)", len(names), out_file, ref
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate the OSRS animation (sequence) name JSON dump."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=config.DOCS_SEQUENCE_NAMES_FILE,
        help="File to write the dump to.",
    )
    parser.add_argument(
        "--ref", default=RUNELITE_REF, help="RuneLite commit to read the names from."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Read a local AnimationID.java instead of fetching it.",
    )
    args = parser.parse_args()

    begin_run("scripts_sequences_update")
    generate(
        out_file=args.out,
        license_file=config.DOCS_SEQUENCE_NAMES_LICENSE,
        ref=args.ref,
        source_file=args.source,
    )


if __name__ == "__main__":
    main()
