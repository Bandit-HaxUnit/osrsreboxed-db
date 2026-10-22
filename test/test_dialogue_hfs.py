import json

import config
from scripts.dialogues import fetch as fetch_module
from scripts.dialogues import update


def test_fetch_discovers_miniquest_transcript_category(monkeypatch):
    queried = []
    downloaded = []

    class FakeTitles:
        def __init__(self, api, categories):
            self.category = categories[0]
            queried.append(self.category)

        def extract_page_titles(self):
            pass

        def __iter__(self):
            titles = {
                "NPC dialogue": ["Transcript:Bob"],
                "Quest transcript": ["Transcript:Quest"],
                "Miniquest transcript": ["Transcript:His Faithful Servants"],
            }
            return iter(titles[self.category])

    class FakeText:
        def __init__(self, api, prefix):
            self.session = object()

    def fake_download(names, path, session, refresh=False):
        downloaded.append((set(names), path))
        return {name: {"wikitext": ""} for name in names}

    monkeypatch.setattr(fetch_module, "WikiPageTitles", FakeTitles)
    monkeypatch.setattr(fetch_module, "WikiPageText", FakeText)
    monkeypatch.setattr(fetch_module, "download", fake_download)
    monkeypatch.setattr(fetch_module, "save", lambda *args, **kwargs: None)

    fetch_module.fetch()

    assert "Miniquest transcript" in queried
    assert any(
        "Transcript:His Faithful Servants" in names and path == fetch_module.QUEST_CACHE
        for names, path in downloaded
    )


CLAIM_LATER = "giving-the-strange-icon-if-the-player-claims-the-lamp-or-map-later"


def test_cached_full_hfs_page_parses_claim_later_reclaim_nodes():
    pages = json.loads(
        (config.DATA_PATH / "dialogues" / "quest-pages.json").read_text()
    )
    page = pages["Transcript:His Faithful Servants"]
    assert "==Giving the strange icon==" in page["wikitext"]
    assert "===If the player claims the lamp or map later===" in page["wikitext"]

    record = update.gameplay_npc(
        "His Faithful Servants",
        update.parse_npc("His Faithful Servants", page["wikitext"]),
    )
    assert record["default"] == "starting-out-talking-to-the-strange-old-man"
    claims = [key for key in record["variants"] if key.endswith(CLAIM_LATER)]
    assert claims == [CLAIM_LATER]

    steps = record["variants"][CLAIM_LATER]
    assert steps[:6] == [
        {
            "type": "line",
            "speaker": "Strange Old Man",
            "text": "This is for you. Take it! Take it!",
        },
        {
            "type": "condition",
            "text": "If the player has not claimed the lamp nor the map:",
            "steps": [
                {
                    "type": "message",
                    "text": "The Strange Old Man has given you a lamp and a map.",
                },
                {"type": "jump", "reference": "continues"},
            ],
        },
        {
            "type": "condition",
            "text": "If the player has not claimed the lamp:",
            "steps": [
                {
                    "type": "message",
                    "text": "The Strange Old Man has given you a lamp.",
                },
                {"type": "jump", "reference": "continues"},
            ],
        },
        {
            "type": "condition",
            "text": "If the player has not claimed the map:",
            "steps": [
                {
                    "type": "message",
                    "text": "The Strange Old Man has given you a map.",
                },
                {"type": "jump", "reference": "continues"},
            ],
        },
        {"player": "Thanks."},
        {
            "type": "choice",
            "options": [
                {
                    "text": "Can you tell me more about the brothers?",
                    "steps": [{"type": "jump", "reference": "above"}],
                },
                {
                    "text": "I wanted to ask you about warnings.",
                    "steps": [{"type": "jump", "reference": "above"}],
                },
                {
                    "text": "I'll leave you to it then...",
                    "steps": [
                        {"player": "I'll leave you to it then..."},
                        {"type": "end"},
                    ],
                },
            ],
        },
    ]


def test_generated_hfs_record_selects_one_claim_later_variant():
    data = json.loads((config.DOCS_PATH / "npc-dialogues.json").read_text())
    record = data["His Faithful Servants"]
    assert record["default"] == "starting-out-talking-to-the-strange-old-man"
    assert [key for key in record["variants"] if key.endswith(CLAIM_LATER)] == [
        CLAIM_LATER
    ]

    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(node.get("steps", []))
            yield from walk(node.get("options", []))

    messages = [
        node.get("text")
        for node in walk(record["variants"][CLAIM_LATER])
        if node.get("type") == "message"
    ]
    assert messages == [
        "The Strange Old Man has given you a lamp and a map.",
        "The Strange Old Man has given you a lamp.",
        "The Strange Old Man has given you a map.",
    ]
