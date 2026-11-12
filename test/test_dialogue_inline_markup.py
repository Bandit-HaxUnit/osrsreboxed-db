import json

import config
from scripts.dialogues.update import clean, parse_step


def test_leading_asterisk_is_speech_not_a_list_marker():
    assert clean("*Sighs*... Fine.") == "*Sighs*... Fine."
    assert clean("*hic* Woops...") == "*hic* Woops..."
    assert clean("* BURP *") == "* BURP *"
    assert (
        clean("Ah that makes sense. *Sighs* You") == "Ah that makes sense. *Sighs* You"
    )


def test_speech_keeps_its_leading_asterisk_and_markup_is_still_stripped():
    node = parse_step("'''Burntof:''' *Whispers* We'll play [[upstairs]].", [], 1)
    assert node["text"] == "*Whispers* We'll play upstairs."
    assert clean("'''Bold''' *still*") == "Bold *still*"


def test_citation_templates_are_not_spoken():
    assert clean("Ice Mountain.{{fact}}") == "Ice Mountain."
    assert clean("Level 42{{Fact|Confirm this}} Magic:") == "Level 42 Magic:"
    assert clean("Kept{{citation needed}}") == "Kept"
    assert clean("Unknown {{mystery}}") == "Unknown {{mystery}}"


def test_footnotes_are_not_spoken():
    # Black Knights' Fortress's cat: "Meow!" in every capture, with the Wiki's catspeak note.
    assert (
        clean('Meow!<ref name="catspeak">No special dialogue with catspeak amulet equipped</ref>')
        == "Meow!"
    )
    assert clean('Purrr....<ref name="catspeak"/>') == "Purrr...."
    assert clean("Hello.<ref>A [[note]].</ref> Bye.") == "Hello. Bye."


def speech(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("npc", "player", "text") and isinstance(value, str):
                found.add(value)
            elif key == "prompt" and isinstance(value, str):
                found.add(value)
            else:
                speech(value, found)
    elif isinstance(node, list):
        for value in node:
            speech(value, found)
    return found


def test_captured_wording_is_exported():
    data = json.loads(
        (config.DOCS_PATH / "npc-dialogues.json").read_text(encoding="utf-8")
    )
    below_ice = speech(data["Below Ice Mountain"], set())
    assert {
        "*Sighs*... Fine. If I go get you this sandwich, will you help Willow?",
        "*Whispers* We'll have the game upshtairs away from everyone.",
        "*hic* Woops...",
        "That would be me, [sir/miss]. What can I do for you?",
        "Of course madam, I will get to work.",
        "Start the Below Ice Mountain quest?",
        "Would you like to start your training session?",
        "Head into the ruins?",
    } <= below_ice
    assert not [text for text in below_ice if "{{fact}}" in text]
    fortress = data["Black Knights' Fortress"]["variants"]
    door = fortress[
        "infiltrating-the-fortress-trying-to-open-the-sturdy-door-while-not-wearing-a-disguise"
    ][1]["options"][0]["steps"]
    assert door[0] == {"player": "Yes, but I work here!"}
    assert door[1]["text"].startswith(
        "I might be new here but I can tell that's not true!"
    )
    assert "No need to... get upset... you're scaring the cat." in speech(
        fortress, set()
    )
    # The revision 242 capture of the whole quest.
    grill = fortress["listen-at-grill"]
    assert grill[6]["text"] == "...not to mention the trees!"
    assert grill[8] == {"type": "line", "speaker": "Greldo", "text": "Yeth, Mithtreth."}
    assert fortress["starting-out-speaking-to-sir-amik-varze-again"][-1]["text"] == (
        "Don't forget to read that dossier of information I gave you."
    )
    assert "Meow!" in speech(fortress, set())
    assert not [text for text in speech(fortress, set()) if "catspeak" in text]
    assert "Sir Amik hands you 2500 coins." not in speech(fortress, set())
