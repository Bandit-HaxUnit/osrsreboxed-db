"""
Which items the wiki says cannot be alchemised.

The item infobox says so per version ("alchable1 = Yes", "alchable2 = No"), or once for every
version ("alchable = No"). That is used first. Without it, the item falls back to
data/items/items-unalchable.json, the page titles in the wiki category "Items that cannot be
alchemised": a versioned item's wiki_name ("Dragon defender (Normal)") is not a page title, so
it is matched by its page name too. The category is per page, so it is only the fallback: a page
lands in it when any one version is unalchable (Mining helmet: Unlit is alchable, Lit is not).
"""

from typing import Optional
from urllib.parse import unquote


def infobox_alchable(value: Optional[str]) -> Optional[bool]:
    """An infobox "alchable" value as True/False, or None when absent or unclear."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text.startswith("yes"):
        return True
    if text.startswith("no"):
        return False
    return None


def is_unalchable(
    unalchable, wiki_name: Optional[str], wiki_page_name: Optional[str] = None,
    wiki_versioned_name: Optional[str] = None, alchable: Optional[bool] = None
) -> bool:
    """True when the item cannot be alchemised (see the module docstring)."""
    if alchable is not None:
        return not alchable
    return any(
        name is not None and name in unalchable
        for name in (wiki_name, wiki_page_name, wiki_versioned_name)
    )


def page_name_from_url(wiki_url: Optional[str]) -> Optional[str]:
    """The wiki page title from an item's wiki_url ("…/w/Dragon_defender#Normal")."""
    if not wiki_url or "/w/" not in wiki_url:
        return None
    return unquote(wiki_url.split("/w/", 1)[1].split("#", 1)[0]).replace("_", " ")


def version_from_url(wiki_url: Optional[str]) -> Optional[str]:
    """The infobox version name from an item's wiki_url ("…#Normal"), or None."""
    if not wiki_url or "#" not in wiki_url:
        return None
    return unquote(wiki_url.split("#", 1)[1]).replace("_", " ")
