import json

import config
from scripts.dialogues.update import clean, parse_step


def test_clean_keeps_a_hex_colour_only_when_asked():
    raw = "{{Colour|#000080|Indeed you have.}}"
    assert clean(raw) == "Indeed you have."
    assert clean(raw, colours=True) == "<col=000080>Indeed you have.</col>"
    # A named colour has no client tag: the text stays plain.
    assert clean("{{Colour|red|Stop!}}", colours=True) == "Stop!"
    assert clean("You hear {{Color|#FF0000|this}}.", colours=True) == "You hear <col=ff0000>this</col>."


def test_a_coloured_line_and_box_carry_styled_text_beside_the_plain_text():
    line = parse_step("'''Veos' Client:''' {{Colour|#000080|Indeed you have.}}", [], 1)
    assert line["text"] == "Indeed you have."
    assert line["styled"] == "<col=000080>Indeed you have.</col>"
    box = parse_step(
        "{{tbox|You hear a whisper in your ear. {{Colour|#000080|'Return... to Veos. My thanks...'}}}}", [], 1
    )
    assert box["text"] == "You hear a whisper in your ear. 'Return... to Veos. My thanks...'"
    assert box["styled"] == "You hear a whisper in your ear. <col=000080>'Return... to Veos. My thanks...'</col>"
    plain = parse_step("'''Veos:''' See you soon.", [], 1)
    assert "styled" not in plain


def walk(steps):
    for step in steps:
        yield step
        yield from walk(step.get("steps", []))
        for option in step.get("options", []):
            yield from walk(option.get("steps", []))


def test_client_of_kourend_exports_the_possessed_veos_colour_and_the_store_menus():
    data = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text(encoding="utf-8"))
    record = data["Client of Kourend"]
    finishing = list(walk(record["variants"]["finishing-up"]))
    client = [s for s in finishing if s.get("speaker") == "Veos' Client"]
    assert len(client) == 6
    assert all(s["styled"] == f"<col=000080>{s['text']}</col>" for s in client)
    orb = list(walk(record["variants"]["activating-the-orb-using-the-activate-option-on-the-mysterious-orb-by-the-dark-altar"]))
    whisper = [s for s in orb if s.get("type") == "message" and s["text"].startswith("You hear a whisper")]
    assert whisper and whisper[0]["styled"].endswith("<col=000080>'Return... to Veos. My thanks...'</col>")
    # RSProx captures local 1001998/1002104: after the first question's answer each store owner's
    # city menu shows again ({{tact|other}}), not the store's opening menu.
    for variant in (
        "leenz-the-port-piscarilius-general-store-owner",
        "horace-the-hosidius-general-store-owner",
        "jennifer-the-shayzien-general-store-owner",
        "munty-the-lovakengj-general-store-owner",
        "regath-the-arceuus-general-store-owner",
    ):
        references = [s["reference"] for s in walk(record["variants"][variant]) if s.get("type") == "jump"]
        assert "other" in references and "previous" not in references, variant
