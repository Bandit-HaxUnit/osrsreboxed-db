"""Historical wiki IDs (``histNNNN``) resolve to their infobox version.

The Guard page lists the Falador longbow guard as ``id9 = 11947,hist3272``.
Dropping the historical token made cache NPC 3272 fall back to the page-name
lookup and receive the first (Edgeville) infobox: melee stats, no arrow.
"""

import json

from scripts.wiki.wikitext_parser import WikitextIDParser, WikitextTemplateParser


def parse(wikitext):
    parser = WikitextTemplateParser(wikitext)
    assert parser.extract_infobox("infobox monster")
    parser.determine_infobox_versions()
    return parser


def test_unversioned_historical_id_is_optional():
    parser = parse("{{Infobox Monster|name = Guard|id = 11947,hist3272}}")
    assert parser.extract_infobox_ids() == {11947: ""}
    assert parser.extract_infobox_ids(include_historical=True) == {11947: "", 3272: ""}


def test_versioned_historical_id_resolves_to_its_version():
    wikitext = (
        "{{Infobox Monster|name = Guard"
        "|id1 = 3269|id2 = 11942|id3 = 3273|id4 = 11947,hist3272}}"
    )
    parser = parse(wikitext)
    ids = parser.extract_infobox_ids(include_historical=True)
    assert ids[11947] == 4
    assert ids[3272] == 4


def test_historical_id_never_overwrites_a_current_id(tmp_path):
    pages = {
        "Derwen": "{{Infobox Monster|name = Derwen|id = 7859}}",
        "Guard": "{{Infobox Monster|name = Guard|id = 11947,hist3272}}",
        "Demon of Balance": "{{Infobox Monster|name = Demon of Balance|id = hist7859}}",
    }
    text_file = tmp_path / "pages.json"
    text_file.write_text(json.dumps(pages))
    parser = WikitextIDParser(text_file, ["infobox monster"])
    parser.process_osrswiki_data_dump()

    assert parser.item_id_to_wiki_name[7859] == "Derwen"
    assert parser.item_id_to_wiki_name[3272] == "Guard"
