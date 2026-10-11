"""
Description:
Read scenery examine text out of OSRS Wiki page wikitext.

OSRS sends an object's examine from the server, so the cache has none of it; the
wiki's ``{{Infobox Scenery}}`` gives it per version, with the object IDs each
version covers (``|id1 = 1276`` / ``|examine1 = One of the most common trees in
Gielinor.``).

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

import re
from typing import Dict, List, Tuple

import mwparserfromhell as mw

INFOBOX_NAME = "infobox scenery"

# What the wiki writes when a scenery object has no examine.
NO_EXAMINE = {"N/A", "None"}

# One text for the two states of a loc whose states are separate IDs, as the
# Fireplace page has it. The world's fireplaces have no Light option: lit.
LIT_STATES = re.compile(r"^\(Unlit\) (.+?) \(Lit\) (.+)$")

NUMBERED_PARAM = re.compile(r"^(?:id|examine|version)(\d+)$")

# A line naming where its text applies ("Throne Room: You can build ..."), when a
# page lists one object's examine per situation, one per line.
SITUATION_LABEL = re.compile(r"^[A-Z][\w' ]{0,30}: ")


def infoboxes(wikitext: str) -> List[Dict[str, str]]:
    """Every ``{{Infobox Scenery}}`` on a page, as its parameters by lowercase name."""
    boxes = []
    for template in mw.parse(wikitext).filter_templates(recursive=True):
        if template.name.strip().lower() != INFOBOX_NAME:
            continue
        boxes.append(
            {
                str(param.name).strip().lower(): str(param.value).strip()
                for param in template.params
            }
        )
    return boxes


def strip_markup(markup: str) -> str:
    """One line of wikitext as plain text: no links, formatting, tags or refs."""
    code = mw.parse(re.sub(r"<br\s*/?>", " ", markup, flags=re.IGNORECASE))
    for tag in code.filter_tags(recursive=False):
        if str(tag.tag).lower() == "ref":
            code.remove(tag)
    text = code.strip_code(normalize=True, collapse=True).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def plain_text(markup: str) -> str:
    """An examine as the text a player reads. A page listing several for one object,
    one per line (as bullets, or labelled by situation: "Throne Room: ..."), gets the
    first: the game sends one of them, not all."""
    lines = [strip_markup(line).lstrip("*").strip() for line in markup.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    if len(lines) > 1 and all(SITUATION_LABEL.match(line) for line in lines):
        return SITUATION_LABEL.sub("", lines[0], count=1)
    return lines[0]


def lit_state(text: str) -> str:
    """The lit half of an "(Unlit) ... (Lit) ..." text; any other text as it is."""
    states = LIT_STATES.match(text)
    return states.group(2) if states else text


def ids_of(value: str) -> List[int]:
    """The object IDs in an ``id`` parameter: comma separated, anything else ignored."""
    return [int(part) for part in (p.strip() for p in value.split(",")) if part.isdigit()]


def examines_of(box: Dict[str, str]) -> List[Tuple[int, str]]:
    """An infobox's object IDs with their examine: per version (``id1``/``examine1``
    ...), falling back to the unnumbered ``id``/``examine``."""
    versions = sorted(
        {int(match.group(1)) for match in map(NUMBERED_PARAM.match, box) if match}
    )
    pairs = []

    def add(id_value: str, examine_value: str) -> None:
        text = lit_state(plain_text(examine_value or ""))
        if not text or text in NO_EXAMINE:
            return
        pairs.extend((object_id, text) for object_id in ids_of(id_value or ""))

    if not versions:
        add(box.get("id", ""), box.get("examine", ""))
        return pairs
    for version in versions:
        add(
            box.get(f"id{version}", box.get("id", "")),
            box.get(f"examine{version}", box.get("examine", "")),
        )
    return pairs
