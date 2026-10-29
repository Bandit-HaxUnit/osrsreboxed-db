"""Export challenge-scroll answers from captured Wiki source (GPL-3.0-or-later).

Rows are keyed by the cache's `cluehelper_challenge_question` row names, matched to
the Wiki solution asking the same question. Several cache rows share one question
(cipher steps, Nieve and Steve), so names never decide the match. The reviewed cache
fixture also carries the cache's own answers; every Wiki answer must agree with them
except for disagreements listed in REVIEWED_DISAGREEMENTS.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import mwparserfromhell as mw

from scripts.drops.reward_caskets import ROOT

SOURCES = Path(__file__).with_name("sources")
WIKI_SOURCE = "challenge-scrolls.wikitext"
CACHE_SOURCE = "challenge-questions-cache.json"
WIKI_URL = "https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Challenge_scrolls"
# Wiki revision of the captured source; update together with a recapture.
WIKI_REVISION = 15285563
HEADING = re.compile(r"^===\s*List of (\w+) solutions\s*===\s*$", re.I)
TIERS = ("medium", "hard", "elite")
NOTE = re.compile(r"'''Note:'''", re.I)
ALTERNATE = re.compile(
    r"If (?P<condition>.+?), the answer is '''(?P<answer>[\d,]+)''' instead of "
    r"'''(?P<instead>[\d,]+)'''\.?",
    re.S,
)
# Key -> (Wiki answers, cache answers), reviewed against the Wiki's own pages.
# Old crone's page also says 619; the cache's 623 is unexplained.
REVIEWED_DISAGREEMENTS = {
    "cluehelper_challenge_question_old_crone": ([619], [623]),
}


def _text(raw):
    """Visible text of a cell: links, formatting and footnotes removed."""
    code = mw.parse(raw)
    for tag in code.filter_tags(recursive=False):
        if str(tag.tag).strip().casefold() == "ref":
            code.remove(tag)
    return re.sub(r"\s+", " ", code.strip_code()).strip()


def _number(raw):
    if not re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+", raw):
        raise ValueError("Unsupported challenge answer: " + raw)
    return int(raw.replace(",", ""))


def _question_key(question):
    return re.sub(r"\s+", " ", question).strip().casefold()


def _rows(lines):
    """Cells of each `|-` row; a cell continues until the next `|` line."""
    rows, cells = [], None
    for line in lines:
        if line.startswith("|-") or line.startswith("|}"):
            if cells:
                rows.append(cells)
            cells = [] if line.startswith("|-") else None
        elif cells is not None and line.startswith("|"):
            cells.append(line[1:])
        elif cells:
            cells[-1] += "\n" + line
    return rows


def _solution(tier, cells):
    if len(cells) != 3:
        raise ValueError("Challenge row must have 3 cells: " + " | ".join(cells))
    npc, question, answer = cells
    parts = NOTE.split(question)
    if len(parts) > 2:
        raise ValueError("Challenge question has several notes: " + question)
    row = {
        "tier": tier,
        "npc": _text(npc),
        "question": _text(parts[0]),
        "answer": _number(answer.strip()),
    }
    if len(parts) == 2:
        note = ALTERNATE.fullmatch(parts[1].strip())
        if not note or _number(note["instead"]) != row["answer"]:
            raise ValueError("Unsupported challenge note: " + parts[1].strip())
        row["alternates"] = [
            {"answer": _number(note["answer"]), "condition": _text(note["condition"])}
        ]
    if not row["npc"] or not row["question"]:
        raise ValueError("Incomplete challenge row: " + " | ".join(cells))
    return row


def parse_wiki(source):
    """Every solution in the Wiki's per-tier tables, in source order."""
    solutions, tier, table, tiers = [], None, None, []
    for line in source.splitlines():
        heading = HEADING.match(line)
        if heading:
            tier = heading[1].casefold()
            if tier not in TIERS:
                raise ValueError("Unsupported challenge tier: " + heading[1])
            tiers.append(tier)
        elif line.startswith("{|"):
            if tier is None:
                raise ValueError("Challenge table without a tier heading")
            table = []
        elif table is not None:
            table.append(line)
            if line.startswith("|}"):
                solutions += [_solution(tier, cells) for cells in _rows(table)]
                tier, table = None, None
    if tiers != list(TIERS):
        raise ValueError("Expected challenge tables for each tier: " + str(tiers))
    return solutions


def build_challenges(source, cache_rows):
    by_question = {}
    for solution in parse_wiki(source):
        by_question.setdefault(_question_key(solution["question"]), []).append(solution)
    challenges = []
    for cache_row in cache_rows:
        key = cache_row["key"]
        questions = {_question_key(v["question"]) for v in cache_row["variants"]}
        if len(questions) != 1:
            raise ValueError("Cache row asks several questions: " + key)
        matches = by_question.get(questions.pop(), [])
        if not matches:
            raise ValueError("No Wiki answer for " + key)
        if len(matches) > 1:
            raise ValueError("Ambiguous Wiki answer for " + key)
        row = {"key": key, **matches[0]}
        wiki = sorted(
            {row["answer"]} | {a["answer"] for a in row.get("alternates", [])}
        )
        cache = sorted({variant["answer"] for variant in cache_row["variants"]})
        if wiki != cache:
            if REVIEWED_DISAGREEMENTS.get(key) != (wiki, cache):
                raise ValueError(
                    "Wiki answer {} disagrees with cache {} for {}".format(
                        wiki, cache, key
                    )
                )
            row["cache_answers"] = cache
        challenges.append(row)
    return challenges


def generate(sources, output):
    # Universal-newline reads make provenance stable across Git checkout modes.
    wiki_text = (sources / WIKI_SOURCE).read_text(encoding="utf-8")
    cache_text = (sources / CACHE_SOURCE).read_text(encoding="utf-8")
    cache = json.loads(cache_text)
    challenges = build_challenges(wiki_text, cache["rows"])
    payload = {
        "schema_version": 1,
        "meta": {
            "sources": {
                "wiki": {
                    "url": WIKI_URL,
                    "revision": WIKI_REVISION,
                    "sha256": hashlib.sha256(wiki_text.encode("utf-8")).hexdigest(),
                },
                "cache": {
                    **cache["source"],
                    "sha256": hashlib.sha256(cache_text.encode("utf-8")).hexdigest(),
                },
            },
            "license": "CC BY-NC-SA 3.0 — Old School RuneScape Wiki contributors",
            "hash_encoding": "UTF-8 with LF newlines",
            "alternates": "State-dependent answers the cache also lists for the row",
            "cache_disagreements": [
                {
                    "key": row["key"],
                    "wiki": [row["answer"]],
                    "cache": row["cache_answers"],
                }
                for row in challenges
                if "cache_answers" in row
            ],
        },
        "challenges": challenges,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "docs/drops-json/clue-challenges.json"
    )
    args = parser.parse_args()
    generate(args.sources, args.out)


if __name__ == "__main__":
    main()
