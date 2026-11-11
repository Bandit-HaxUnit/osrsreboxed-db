"""
Author:  PH01L
Email:   phoil@osrsbox.com
Website: https://www.osrsbox.com

Description:
Various methods to help clean OSRS Wiki wikitext entries.

Copyright (c) 2021, PH01L

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


from dateutil.parser import parse as date_parse


def clean_wikitext(value: str) -> str:
    """Generic infobox property cleaner.

    This helper method is a generic cleaner for all infobox template properties.
    The value is string cast, stipped of new line characters, then any square
    brackets (wikitext links) are stripped, then anything in trailing brackets,
    then any HTML line breaks are removed, and wiki templates are removed.

    :param value: Template value extracted in raw wikitext format.
    :return value: Cleaned template value.
    """
    value = str(value)
    value = value.strip()
    value = re.sub(r"[\[\]]+", "", value)  # Removes all "[" and "]"
    value = re.sub(r" \([^()]*\)", "", value)  # Removes " (anything)"
    value = re.sub(r"<!--(.*?)-->", "", value)  # Removes "<!--anything-->"
    value = re.sub(r"<br(.*)", "", value)  # Removes "<br"
    value = re.sub(r"\{\{.*?\}\}", "", value)  # Removes wiki templates {{ }}
    return value


def caller(value: str, prop: str):
    """Calls specific function based on property name.

    Since there is a dict loop method to reduce code duplication,
    there needs to be a way to call the function that matches the
    property. This helps call the function and return the cleaned
    values.

    :param value: Template value extracted in raw wikitext format.
    :param prop: The template property being processed.
    :return value: Cleaned template value.
    """
    value = globals()[prop](value)
    return value


def members(value: str) -> bool:
    """Convert the members property to a boolean.

    :param value: Template value extracted from raw wikitext.
    :return value: Template value converted into a boolean.
    """
    try:
        if value.lower() in ["true", "yes"]:
            return True
        else:
            return False
    except AttributeError:
        return False


def release_date(value: str) -> str:
    """Convert the release date entry to an ISO 8601 date str.

    From the wiki, the usual date format is: dd Month YYYY
    But it will have wikitext markup: [[31 October]] [[2005]]
    Returned value is ISO 8601 date string: YYYY-MM-DD

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned release date in ISO 8601 date format.
    """
    if not value:
        return None

    value = value.replace("[", "").replace("]", "")

    try:
        return date_parse(value).date().isoformat()
    except (ValueError, AttributeError):
        return None


def hitpoints(value: str) -> int:
    """Convert the hitpoints entry to an integer.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned hitpoints value as an integer.
    """
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def _numbers(value: str) -> list:
    return [int(number) for number in re.findall(r"\d+", value)]


def max_hit(value: str) -> int:
    """Convert the max_hit entry to an integer.

    The Wiki documents this field as "the monster's maximum hit, comma
    separated list". The export has one integer, so the established contract is
    the first listed value (the primary/auto attack). ``{{plainlist}}`` may
    label the entries; prefer the explicit auto attack, otherwise the highest
    listed value, which is the monster's actual maximum across mixed styles.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned max_hit value as an integer.
    """
    if not value:
        return None

    if "plainlist" in value.lower():
        bullets = [
            line.strip()[1:].strip()
            for line in value.splitlines()
            if line.strip().startswith("*")
        ]
        auto = next((bullet for bullet in bullets if "auto" in bullet.lower()), None)
        if auto is not None:
            numbers = _numbers(auto)
            return numbers[0] if numbers else None
        numbers = [number for bullet in bullets for number in _numbers(bullet)]
        return max(numbers) if numbers else None

    # Keep the existing "first token" contract: alternatives are separated by a
    # comma or space. A leading damage range contributes its maximum, but a
    # decreasing range is not a valid maximum and stays unset.
    token = re.split("[ ,]", value)[0]
    range_match = re.fullmatch(r"(\d+)[-\u2013\u2014](\d+)", token)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        return high if high > low else None

    try:
        return int(token)
    except ValueError:
        return None


def attack_type(value: str) -> list:
    """Convert the attack type entry to a list of strings.

    :param value: The extracted raw wiki text.
    :return value: A cleaned attack_type value as a list of strings.
    """
    value_list = []

    if value is None or value == "":
        return value_list

    value = value.lower()
    value = value.replace("[", "").replace("]", "")

    # The Wiki uses "All" for a monster that attacks with every style.
    if value.strip() == "all":
        return ["melee", "ranged", "magic"]

    # Check for specific attack type strings...
    if "melee" in value:
        value_list.append("melee")
    if "slash" in value:
        value_list.append("slash")
    if "crush" in value:
        value_list.append("crush")
    if "stab" in value:
        value_list.append("stab")
    if "ranged" in value:
        value_list.append("ranged")
    if "magic" in value:
        value_list.append("magic")
    if "typeless" in value:
        value_list.append("typeless")
    if "dragonfire" in value:
        value_list.append("dragonfire")

    return value_list


def attack_speed(value: str) -> int:
    """Convert the attack_speed entry to an integer.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned attack_speed value as an integer.
    """
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def aggressive(value: str) -> bool:
    """Convert the aggressive property to a boolean.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned aggressive value as a boolean.
    """
    value = clean_wikitext(value)

    if value.lower() in ["true", "yes"]:
        return True
    elif value.split(" ")[0].lower in ["true", "yes"]:
        return True
    else:
        return False


def poisonous(value: str) -> bool:
    """Convert the poisonous property to a boolean.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned poisonous value as a boolean.
    """
    if not value:
        return False

    value = clean_wikitext(value)

    if value.lower() in ["true", "yes"]:
        return True
    elif value.split(" ")[0].lower in ["true", "yes"]:
        return True
    else:
        return False


def venomous(value: str) -> bool:
    """Convert the venomous property to a boolean.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned venomous value as a boolean.
    """
    if not value:
        return False

    if "venom" in value.lower():
        return True
    else:
        return False


def _full_status_resistance(value: str) -> bool:
    if not value:
        return False
    value = value.strip().lower()
    if value in ["true", "yes"]:
        return True
    try:
        return int(value) >= 100
    except ValueError:
        return False


def immune_poison(value: str) -> bool:
    """Convert the immune_poison property to a boolean.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned immune_poison value as a boolean.
    """
    return _full_status_resistance(value)


def immune_venom(value: str) -> bool:
    """Convert the immune_venom property to a boolean.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned immune_venom value as a boolean.
    """
    # The current Wiki uses "Poison" when venom becomes ordinary poison.
    # This is venom immunity, independently of poison susceptibility.
    return _full_status_resistance(value) or bool(
        value and value.strip().lower() == "poison"
    )


def freeze_resistance(value: str) -> int:
    """Convert the freeze_resistance property to a whole percentage.

    The Wiki's ``freezeresistance`` reduces the duration of freezes (bind, snare,
    entangle and ice spells): 33 means a third shorter, 100 means the monster
    is never frozen (Wiki: Freeze). A missing or unreadable value is no resistance.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned freeze_resistance value, from 0 to 100.
    """
    if not value:
        return 0
    value = value.strip().lower()
    if value in ["true", "yes"]:
        return 100
    match = re.match(r"^(\d+)\s*%?$", value)
    if not match:
        return 0
    return min(int(match.group(1)), 100)


def attributes(value: str) -> str:
    """Convert the attributes text entry to a list.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned attributes value as a list.
    """
    attributes_list = []

    if value is None or value == "":
        return attributes_list

    value = value.lower()

    # Check for specific melee attack types
    if "demon" in value:
        attributes_list.append("demon")
    if "dragon" in value:
        attributes_list.append("dragon")
    if "fiery" in value:
        attributes_list.append("fiery")
    if "golem" in value:
        attributes_list.append("golem")
    if "kalphite" in value:
        attributes_list.append("kalphite")
    if "leafy" in value:
        attributes_list.append("leafy")
    if "penance" in value:
        attributes_list.append("penance")
    if "shade" in value:
        attributes_list.append("shade")
    if "spectral" in value:
        attributes_list.append("spectral")
    if "undead" in value:
        attributes_list.append("undead")
    if "vampyre" in value:
        attributes_list.append("vampyre")
    if "xerician" in value:
        attributes_list.append("xerician")

    return attributes_list


def categories_to_attributes(categories) -> list:
    """Map captured Wiki page categories to the monster attribute list."""
    return attributes(" ".join(categories))


def category(value: str) -> str:
    """Convert the category text entry from an OSRS Wiki infobox.

    :param value: The extracted raw wiki text.
    :return: A cleaned categories property value.
    """
    category_list = []

    if value is None or value == "" or value.lower() == "no" or "<!--" in value:
        return category_list

    value = clean_wikitext(value)

    value = value.lower()

    if "|" in value:
        value = value.split("|")[1]

    value_list = None
    if "," in value:
        value_list = []
        for v in value.split(","):
            v = v.strip()
            value_list.append(v)

    if value_list:
        for value in value_list:
            category_list.append(value)
    else:
        category_list.append(value)

    return category_list


def slayer_level(value: str) -> int:
    """Convert the slayer_level entry to an integer.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned slayer_level value as an integer.
    """
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def slayer_xp(value: str) -> float:
    """Convert the slayer_xp entry to a float.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned slayer_xp value as a float.
    """
    if not value:
        return None

    value = clean_wikitext(value)

    try:
        return float(value)
    except ValueError:
        return None


def slayer_masters(value: str) -> float:
    """Convert the slayer_masters entry to a list.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned slayer_masters value as a list.
    """
    slayer_masters = value.strip()

    if slayer_masters.lower().startswith("no") or slayer_masters == "":
        return []

    # Split string into list of strings
    slayer_masters = slayer_masters.split(",")
    slayer_masters = [x.strip() for x in slayer_masters]
    slayer_masters = [x.lower() for x in slayer_masters]

    # Remove Steve, just for consistency
    if "steve" in slayer_masters:
        slayer_masters.remove("steve")
        if "nieve" not in slayer_masters:
            slayer_masters.append("nieve")

    return slayer_masters


def examine(value: str) -> bool:
    """Convert the examine entry to a list.

    :param value: Template value extracted from raw wikitext.
    :return value: A cleaned examine value as a str.
    """
    value = clean_wikitext(value)

    # Quick fix for multiline examine texts
    value = value.split("\n")[0]

    # Remove: brackets, curly braces, spaces, tidle, plus
    value = re.sub(r'[{}\*"]', "", value)

    # Change: three periods style
    value = value.replace("…", "...")

    # Remove: versioned examine text markers
    value = re.sub(r"'{2,}[^']+[']*", "", value)

    # Finally, strip any remaining whitespace
    value = value.strip()

    return value


def stats(value: str) -> int:
    """Convert a monster stat or elemental value to an integer.

    :param value: Template value extracted from raw wikitext.
    :return: A cleaned stat value as an int, or mapped elemental value.
    """
    elemental_map = {"Air": 1, "Water": 2, "Earth": 3, "Fire": 4}

    value = value.strip().capitalize()
    if value in elemental_map:
        return elemental_map[value]

    # Some current Wiki infoboxes give a scaling range (for example
    # ``210-<br />280``); the first value is the canonical base level.
    range_match = re.match(r"\s*(\d+)\s*-\s*<br", value)
    if range_match:
        return int(range_match.group(1))

    try:
        return int(value.strip())
    except ValueError:
        return 0
