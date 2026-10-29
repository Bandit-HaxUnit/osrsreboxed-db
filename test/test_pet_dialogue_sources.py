"""Pet transcripts must enter the same canonical NPC pipeline as other speakers."""

import pytest

from scripts.dialogues import fetch as collector


def collect(monkeypatch, pet_titles):
    categories = {
        "NPC dialogue": ["Transcript:Bob", "Transcript:Shared"],
        "Pet dialogue": pet_titles,
        "Quest transcript": ["Transcript:Quest"],
        "Miniquest transcript": ["Transcript:Miniquest"],
        "Event transcript": ["Transcript:Event"],
    }
    queried, downloads, saved = [], [], []

    class Titles:
        def __init__(self, api, names):
            self.name = names[0]
            queried.append(self.name)

        def extract_page_titles(self):
            pass

        def __iter__(self):
            return iter(categories[self.name])

    class Text:
        def __init__(self, api, prefix):
            self.session = object()

    def download(names, path, session, refresh=False, with_categories=False):
        downloads.append((set(names), path, refresh))
        return {name: {"revision": 1, "wikitext": ""} for name in names}

    monkeypatch.setattr(collector, "WikiPageTitles", Titles)
    monkeypatch.setattr(collector, "WikiPageText", Text)
    monkeypatch.setattr(collector, "download", download)
    monkeypatch.setattr(collector, "save", lambda path, value: saved.append((path, value)))
    return queried, downloads, saved


def test_pet_transcripts_and_identity_pages_use_the_canonical_npc_cache(monkeypatch):
    queried, downloads, saved = collect(monkeypatch, ["Transcript:Olmlet"])
    result = collector.fetch()
    assert "Pet dialogue" in queried
    assert set(result) == {"Transcript:Bob", "Transcript:Shared", "Transcript:Olmlet"}
    assert any(
        path == collector.NPC_CACHE and "Olmlet" in names
        for names, path, _ in downloads
    )
    assert all("Transcript:Olmlet" not in names for names, path, _ in downloads if path == collector.QUEST_CACHE)
    assert set(saved[-1][1]) == set(result)


def test_empty_pet_category_fails_instead_of_publishing_a_silent_partial_export(monkeypatch):
    collect(monkeypatch, [])
    with pytest.raises(ValueError, match="Pet dialogue returned no transcripts"):
        collector.fetch()


def test_cross_listed_pet_pages_are_deduplicated_and_refresh_identity_sources(monkeypatch):
    _, downloads, _ = collect(monkeypatch, ["Transcript:Olmlet", "Transcript:Shared"])
    result = collector.fetch(refresh=True)
    assert len(result) == 3
    assert any(
        path == collector.CACHE
        and names == {"Transcript:Bob", "Transcript:Shared", "Transcript:Olmlet"}
        and refresh
        for names, path, refresh in downloads
    )
    assert any(path == collector.NPC_CACHE and "Olmlet" in names and refresh for names, path, refresh in downloads)


def test_promoted_pet_page_is_removed_from_old_reference_cache(monkeypatch):
    _, _, saved = collect(monkeypatch, ["Transcript:Olmlet"])
    original = collector.download

    def cached_download(names, path, session, refresh=False, with_categories=False):
        result = original(names, path, session, refresh, with_categories)
        if path == collector.QUEST_CACHE:
            result["Transcript:Olmlet"] = {"revision": 0, "wikitext": ""}
        return result

    monkeypatch.setattr(collector, "download", cached_download)
    collector.fetch()
    references = [data for path, data in saved if path == collector.QUEST_CACHE]
    assert references, "promoted NPC transcripts must persist the reference-cache migration"
    assert "Transcript:Olmlet" not in references[-1]
    assert {"Transcript:Quest", "Transcript:Miniquest"} <= set(references[-1])


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("{{Transcript|pet}}", "pet"),
        ("{{ transcript | type= PET }}", "pet"),
        ("{{Transcript|item}}", "item"),
        ("{{Transcript|quest}}", "quest"),
        ("{{Switch|one={{Transcript|pet}}}}{{Transcript|npc}}", "npc"),
        ("{{Transcript}}", "unclassified"),
        ("{{Transcript|pet}}{{Transcript|npc}}", "unclassified"),
    ],
)
def test_transcript_type_uses_only_unambiguous_top_level_source(raw, expected):
    assert collector.transcript_type(raw) == expected


def test_generated_types_match_cached_sources_and_cover_runtime_records():
    import json
    import config

    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    types = read(config.DOCS_PATH / "dialogue-types.json")
    records = read(config.DOCS_PATH / "npc-dialogues.json")
    assert list(types) == sorted(types)
    seen = set()
    sources = {**read(collector.CACHE), **read(collector.QUEST_CACHE)}
    for kind, titles in types.items():
        assert titles == sorted(set(titles))
        assert not seen.intersection(titles)
        seen.update(titles)
        for title in titles:
            if title in sources:
                assert collector.transcript_type(sources[title]["wikitext"]) == kind
            else:
                assert kind == "unclassified", "authored-only records cannot be inferred as pets"
    assert seen == {"Transcript:" + name for name in records}
    assert "Transcript:Olmlet" in types["pet"]
    assert "Transcript:Cook" not in types["pet"]
    assert set(types.get("item", [])).isdisjoint(types["pet"])


@pytest.mark.parametrize("npc_id", [*range(1619, 1626), *range(5591, 5605)])
def test_cat_followers_keep_existing_tail_of_two_cats_chore_entrypoints(npc_id):
    import config

    # Cache241 adult cats, kittens, overgrown cats and their hellcat forms.
    index = collector.read_cache(config.DOCS_PATH / "npc-dialogue-index.json")
    expected = {
        "unferth-s-chores-talking-to-your-cat-about-chores",
        "unferth-s-chores-talking-to-your-cat-after-finishing-the-chores",
    }
    candidates = [row for row in index[str(npc_id)] if row["page"] == "Transcript:A Tail of Two Cats"]
    assert any(expected <= set(row["variants"]) for row in candidates), npc_id
