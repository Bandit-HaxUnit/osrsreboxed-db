"""Holiday transcripts use the same revision/dependency/identity collection pipeline."""

import json

import pytest
import requests

from scripts.dialogues import fetch


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    categories = {
        "NPC dialogue": ["Transcript:Existing NPC"],
        "Quest transcript": ["Transcript:Existing quest"],
        "Event transcript": ["Transcript:2025 Christmas event", "Transcript:Existing NPC"],
    }
    pages = {
        "Transcript:Existing NPC": "* '''Player:''' Hello.",
        "Transcript:Existing quest": "{{Transcript list|Player|Existing NPC}}",
        "Transcript:2025 Christmas event": (
            "{{Transcript list|Player|Cook (Blue Moon Inn)}}\n"
            "[[Transcript:Holiday dependency]]\n* '''Player:''' A fixture meal."
        ),
        "Transcript:Holiday dependency": "* '''Player:''' A fixture reply.",
        "Existing NPC": "{{Infobox NPC|id=1|name=Existing NPC}}",
        "Cook (Blue Moon Inn)": "{{Infobox NPC|id=2895|name=Cook}}",
    }
    calls = []

    class Response:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

        def raise_for_status(self):
            pass

    def get(session, url, *, params, **kwargs):
        calls.append(dict(params))
        if params.get("list") == "categorymembers":
            category = params["cmtitle"].removeprefix("Category:")
            return Response({"query": {"categorymembers": [
                {"title": name} for name in categories[category]
            ]}})
        return Response({"query": {"pages": [
            {"title": title, "revisions": [{"revid": 17, "slots": {
                "main": {"content": pages[title]}
            }}]} if title in pages else {"title": title, "missing": True}
            for title in params["titles"].split("|")
        ]}})

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)
    for key, file in [("CACHE", "npc.json"), ("QUEST_CACHE", "reference.json"),
                      ("NPC_CACHE", "identities.json")]:
        monkeypatch.setattr(fetch, key, tmp_path / file)
    return categories, calls


def test_event_transcripts_follow_real_collector_download_and_identity_paths(wiki):
    result = fetch.fetch()
    assert set(result) == {"Transcript:Existing NPC"}
    reference = fetch.read_cache(fetch.QUEST_CACHE)
    assert reference["Transcript:2025 Christmas event"]["revision"] == 17
    assert "Transcript:Holiday dependency" in reference
    assert "Transcript:Existing NPC" not in reference
    assert "Cook (Blue Moon Inn)" in fetch.read_cache(fetch.NPC_CACHE)
    assert json.loads(fetch.CACHE.read_text()) == result


def test_refresh_fetches_event_roots_once_and_keeps_dependencies(wiki):
    _, calls = wiki
    fetch.fetch()
    calls.clear()
    fetch.fetch(refresh=True)
    title_batches = [call["titles"].split("|") for call in calls if "titles" in call]
    assert sum("Transcript:2025 Christmas event" in batch for batch in title_batches) == 1
    assert sum("Transcript:Holiday dependency" in batch for batch in title_batches) == 1
    assert "Transcript:Holiday dependency" in fetch.read_cache(fetch.QUEST_CACHE)


def test_empty_event_category_fails_before_publishing_source_caches(wiki):
    categories, _ = wiki
    categories["Event transcript"] = []
    with pytest.raises(ValueError, match="Event transcript returned no transcripts"):
        fetch.fetch()
    assert not fetch.CACHE.exists()
    assert not fetch.QUEST_CACHE.exists()
