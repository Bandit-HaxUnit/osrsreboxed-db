"""Real-source contracts for challenge-scroll answers keyed to the cache's rows."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "scripts/drops/sources"
WIKI = SOURCES / "challenge-scrolls.wikitext"
CACHE = SOURCES / "challenge-questions-cache.json"
PREFIX = "cluehelper_challenge_question_"


def wiki_text():
    return WIKI.read_text(encoding="utf-8")


def cache_rows():
    return json.loads(CACHE.read_text(encoding="utf-8"))["rows"]


def build(text=None, rows=None):
    from scripts.drops.clue_challenges import build_challenges

    return build_challenges(
        wiki_text() if text is None else text, cache_rows() if rows is None else rows
    )


def by_key(rows):
    return {row["key"][len(PREFIX) :]: row for row in rows}


def test_reviewed_cache_fixture_lists_every_challenge_row_once():
    fixture = json.loads(CACHE.read_text(encoding="utf-8"))
    assert fixture["source"] == {
        "cache": "osrs-241_2026-10-20",
        "revision": 241,
        "table": "cluehelper_challenge_question",
    }
    keys = [row["key"] for row in fixture["rows"]]
    assert len(keys) == len(set(keys)) == 90
    assert all(key.startswith(PREFIX) for key in keys)
    assert all(row["variants"] for row in fixture["rows"])


def test_every_cache_key_has_an_integer_answer_in_cache_order():
    rows = build()
    assert [row["key"] for row in rows] == [row["key"] for row in cache_rows()]
    for row in rows:
        assert set(row) <= {
            "key",
            "tier",
            "npc",
            "question",
            "answer",
            "alternates",
            "cache_answers",
        }
        assert type(row["answer"]) is int and row["answer"] >= 0, row["key"]
        assert row["npc"] and row["question"], row["key"]
        assert row["tier"] in ("medium", "hard", "elite"), row["key"]


@pytest.mark.parametrize(
    "key,tier,npc,answer",
    [
        ("baraek", "medium", "Baraek", 5),
        ("captain_tobias", "medium", "Captain Tobias", 6),
        ("medium_cryptic_vm02", "medium", "Teicuh", 4097),
        ("cipher_medium_0", "medium", "Ali the Kebab seller", 399),
        ("ali_kebab", "medium", "Ali the Kebab seller", 399),
        ("nieve", "medium", "Nieve/Steve", 2),
        ("steve", "medium", "Nieve/Steve", 2),
        ("cook", "medium", "Cook", 9),
        ("dominic_onion", "medium", "Dominic Onion", 9500),
        ("otto_godblessed_dragons", "medium", "Otto Godblessed", 2),
        ("otto_godblessed_pyres", "hard", "Otto Godblessed", 3),
        ("king_awowogei", "hard", "Awowogei", 24),
        ("capn_izzy_no_beard", "hard", "Cap'n Izzy No-Beard's parrot", 33),
        ("dark_mage", "hard", "Dark mage", 13),
        ("ent", "hard", "Spirit tree", 13112221),
        ("cipher_hard_1", "hard", "Eluned", 53000),
        ("cipher_hard_5", "hard", "Sulisal", 4),
        ("ambassador_alvijar", "elite", "Ambassador Alvijar", 2505),
        ("sigli_the_huntsman", "elite", "Sigli the Huntsman", 302),
    ],
)
def test_keys_resolve_to_the_wiki_row_asking_their_question(key, tier, npc, answer):
    row = by_key(build())[key]
    assert (row["tier"], row["npc"], row["answer"]) == (tier, npc, answer)


def test_wiki_markup_is_stripped_from_questions_and_names():
    rows = by_key(build())
    assert rows["caroline"]["question"] == (
        "How many fishermen are there on the fishing platform?"
    )
    assert rows["zoo_keeper"]["question"] == (
        "How many animals in total are there in the zoo?"
    )
    assert "<ref" not in rows["ali_kebab"]["npc"]
    assert all(
        "[[" not in row["question"] and "''" not in row["question"]
        for row in rows.values()
    )


def test_state_dependent_answers_are_alternates_matching_the_cache_variants():
    rows = by_key(build())
    assert rows["father_aereck"]["answer"] == 19
    assert rows["father_aereck"]["alternates"] == [
        {
            "answer": 20,
            "condition": "players failed to save Jarvis during the 2017 Halloween event",
        }
    ]
    assert rows["zoo_keeper"]["answer"] == 50
    assert rows["zoo_keeper"]["alternates"] == [
        {"answer": 51, "condition": "the player has completed Eagles' Peak"}
    ]
    assert sum("alternates" in row for row in rows.values()) == 2


def test_wiki_answers_agree_with_cache_answers_except_the_reviewed_old_crone():
    rows = build()
    cache = {row["key"]: row for row in cache_rows()}
    for row in rows:
        wiki = {row["answer"]} | {alt["answer"] for alt in row.get("alternates", [])}
        cached = {variant["answer"] for variant in cache[row["key"]]["variants"]}
        if row["key"] == PREFIX + "old_crone":
            assert (row["answer"], row["cache_answers"]) == (619, [623])
            assert wiki != cached
        else:
            assert wiki == cached, row["key"]
            assert "cache_answers" not in row
    assert sum("cache_answers" in row for row in rows) == 1


def test_every_wiki_solution_is_reached_by_a_cache_key():
    from scripts.drops.clue_challenges import parse_wiki

    solutions = parse_wiki(wiki_text())
    assert len(solutions) == 78
    assert [
        sum(row["tier"] == tier for row in solutions)
        for tier in ("medium", "hard", "elite")
    ] == [44, 22, 12]
    used = {(row["tier"], row["npc"], row["question"]) for row in build()}
    assert {(row["tier"], row["npc"], row["question"]) for row in solutions} == used


BARAEK = "|[[Baraek]]\n|''How many stalls are there in Varrock Square?''\n|5\n"


@pytest.mark.parametrize(
    "change,error",
    [
        (
            lambda text: text.replace(BARAEK, "|[[Baraek]]\n|''Elsewhere?''\n|5\n", 1),
            "No Wiki answer.*baraek",
        ),
        (
            lambda text: text.replace(BARAEK, BARAEK.replace("|5\n", "|five\n"), 1),
            "answer",
        ),
        (
            lambda text: text.replace(BARAEK, BARAEK.replace("|5\n", "|6\n"), 1),
            "disagrees.*baraek",
        ),
        (lambda text: text.replace("|619\n", "|620\n", 1), "disagrees.*old_crone"),
        (
            lambda text: text.replace(
                BARAEK, BARAEK + "|-\n" + BARAEK.replace("Baraek", "Gertrude"), 1
            ),
            "Ambiguous",
        ),
        (
            lambda text: text.replace("'''20''' instead", "'''20''' otherwise", 1),
            "note",
        ),
        (
            lambda text: text.replace(
                "===List of Hard solutions===", "===List of Other solutions===", 1
            ),
            "tier",
        ),
        (
            lambda text: text.replace(
                "|-\n|[[Baraek]]", "|-\n|[[Baraek]]\n|extra cell", 1
            ),
            "cells",
        ),
    ],
)
def test_unsupported_or_incomplete_source_fails_closed(change, error):
    text = change(wiki_text())
    assert text != wiki_text()
    with pytest.raises(ValueError, match=error):
        build(text)


def test_cache_key_without_a_wiki_question_fails_closed():
    rows = cache_rows() + [
        {
            "key": PREFIX + "unknown",
            "variants": [{"question": "How many?", "answer": 1}],
        }
    ]
    with pytest.raises(ValueError, match="No Wiki answer.*unknown"):
        build(rows=rows)


def test_generation_is_deterministic_and_records_source_hashes(tmp_path):
    from scripts.drops.clue_challenges import generate

    first, second = tmp_path / "a.json", tmp_path / "b.json"
    for output in (first, second):
        generate(SOURCES, output)
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert len(payload["challenges"]) == 90
    meta = payload["meta"]
    assert meta["sources"]["wiki"]["revision"] == 15285563
    assert (
        meta["sources"]["wiki"]["sha256"]
        == hashlib.sha256(wiki_text().encode("utf-8")).hexdigest()
    )
    assert meta["sources"]["cache"]["revision"] == 241
    assert (
        meta["sources"]["cache"]["sha256"]
        == hashlib.sha256(CACHE.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    )
    assert meta["cache_disagreements"] == [
        {"key": PREFIX + "old_crone", "wiki": [619], "cache": [623]}
    ]
    assert "CC BY-NC-SA" in meta["license"]


def test_invalid_input_preserves_previous_export(tmp_path):
    from scripts.drops.clue_challenges import generate

    (tmp_path / CACHE.name).write_bytes(CACHE.read_bytes())
    (tmp_path / WIKI.name).write_text(
        wiki_text().replace(BARAEK, BARAEK.replace("|5\n", "|6\n"), 1),
        encoding="utf-8",
    )
    output = tmp_path / "retained.json"
    output.write_bytes(b"previous valid artifact")
    with pytest.raises(ValueError, match="disagrees"):
        generate(tmp_path, output)
    assert output.read_bytes() == b"previous valid artifact"


def test_lf_and_crlf_inputs_produce_identical_lf_export(tmp_path):
    from scripts.drops.clue_challenges import generate

    outputs = []
    for label, newline in (("lf", "\n"), ("crlf", "\r\n")):
        root = tmp_path / label
        root.mkdir()
        for path in (WIKI, CACHE):
            text = path.read_text(encoding="utf-8")
            (root / path.name).write_bytes(text.replace("\n", newline).encode("utf-8"))
        output = root / "output.json"
        generate(root, output)
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]
    assert b"\r\n" not in outputs[0]
