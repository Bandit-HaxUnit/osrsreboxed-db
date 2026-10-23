# Beginner casket source capture

`beginner-rewards.tsv` is a reviewed transcription of the factual item names,
quantities, rates and note status in the OSRS Wiki's
[Reward casket (beginner)](https://oldschool.runescape.wiki/w/Reward_casket_(beginner))
rendered reward table, captured through indexed web search on 23 October 2026.
The direct page and API were unavailable in this environment; a revision ID and
raw wikitext could not be retrieved. This is explicitly a rendered-table capture,
not raw Wiki markup. Wiki content attribution: Old School RuneScape Wiki
contributors, CC BY-NC-SA 3.0. Rates cite Mod Tide's 11 October 2019 confirmation.

There are 74 mutually exclusive outcomes per roll: 15 uniques at 1/360 each,
18 black items at 11/8856 each, 40 ordinary outcomes at 11/492 each, and noted
cabbages at 1/24. These sum to exactly one. The black items table has already
been expanded by the Wiki, so its displayed rates must not be applied twice.
The casket grants 1–3 reward rolls. All four food entries are noted.

The Wiki says accounts younger than ten hours cannot receive uniques, but does
not explain the replacement algorithm. The exporter records that uncertainty;
it must not silently claim a reroll or cabbage replacement is authentic.
Black pickaxe is on the black items table, not the age-restricted unique table.

Conditional milestones are separate: minor/major cases at 50/100 completions
(released 2 July 2025; IDs verified from their Wiki item pages), and Explore at
600. Case replacement requires not having opened the case and no longer owning
it; these are not unconditional items on every subsequent completion.

Regenerate using `python -m scripts.drops.reward_caskets --out <path>`.
The source TSV and item database hashes are recorded in the generated metadata.
Both input hashes normalise CRLF to LF, and output always uses LF, so Windows
and Unix checkouts produce identical provenance and export bytes.
Never hand-edit the generated JSON. The standalone exporter uses only Python's
standard library and intentionally does not require NPC source dumps.

# Elite/master raw source captures

`elite-rewards.wikitext` and `master-rewards.wikitext` are the actual raw Wiki
source retrieved on 23 October 2026 from these public URLs through Jina Reader:

- https://oldschool.runescape.wiki/w/Reward_casket_(elite)?action=raw
- https://oldschool.runescape.wiki/w/Reward_casket_(master)?action=raw

Only the reader's response envelope was removed; the source body is retained
unchanged apart from checkout line endings. Response Last-Modified values were
2 October 2026 01:48:04 GMT (elite) and 11 October 2026 21:22:30 GMT (master).
These are not revision IDs. Content: Old School RuneScape Wiki contributors,
CC BY-NC-SA 3.0.

The 182 elite and 173 master normal reward outcomes sum exactly to one when using
the arithmetic branch factors inside the source's reciprocal-denominator
expressions. The trailing `round 1` formats the Wiki display; sampling its
rounded denominators would distort the probabilities. Duplicate coin outcomes
with different quantities remain separate. All names resolve to the canonical
item database. Normal reward rolls are 4–6 elite and 5–7 master; these are distinct
from the Mimic's 5/6 attempt limits and its 1/35 or 1/15 conversion chance.

Mimic rewards and tertiary rewards do not belong in the normal per-roll pool.
The tertiary rows are exported separately with their source eligibility notes;
they require explicit runtime handling, including milestone counts, ownership,
opened scroll cases, master-clue boxes and the Bloodhound pet.

Regenerate with `python -m scripts.drops.clue_caskets --out <path>`; this uses the
existing mwparserfromhell dependency. Source and item database hashes accompany
the output, normalized to UTF-8 with LF newlines. JSON output uses explicit LF
bytes so LF and CRLF input checkouts produce identical artifacts. The beginner
exporter and ordinary NPC drops are unaffected.

# Easy/medium/hard raw source captures

`easy-rewards.wikitext`, `medium-rewards.wikitext` and `hard-rewards.wikitext` are
the raw Wiki source fetched directly with `?action=raw` on 23 October 2026, byte for
byte. Revision IDs come from the MediaWiki API. The elite and master revisions
below were looked up the same day and match the Last-Modified values recorded
above. SHA-256 values are of the UTF-8 text with LF newlines; the exporter records
the same values in `meta.sources`.

| Tier | Revision | Timestamp (UTC) | SHA-256 |
|---|---|---|---|
| easy | 15358923 | 2026-09-30 15:10:07 | `b551c3d56d309c1d47bc9851d7929b1c9362e6ac74db7ef3e062c34c5c27f964` |
| medium | 15358924 | 2026-09-30 15:10:28 | `eb487dc83f25904186ec6891f7da420a542c588ea014f2be955f730c8828117a` |
| hard | 15360008 | 2026-10-02 01:47:14 | `a098bcd72fa39066f1d8932979b884afd5c2af5d96b6a51418c403445fddad1a` |
| elite | 15360009 | 2026-10-02 01:48:04 | `f6ae44487bd522e4067d76822fd94c883264119a5a7ed430232c00f39ec39378` |
| master | 15370773 | 2026-10-11 21:22:30 | `f9fbdcd68f297d1018b57dabf7cdf021ee61c07416a4c372064d7084a84e6cf1` |

Normal pools: easy has 211 outcomes and 2–4 rolls, medium 192 and 3–5, hard 233
and 4–6. Only elite and master have a Mimic sentence. It is required for those two
tiers and rejected for the rest. Easy and medium also have a `Rewards on Entrana`
pool (no uniques, weapons or armour). It sits under its own level-2 heading and is
not exported; a casket opened on Entrana needs separate handling. Tertiary rows stay
separate, as for elite and master. The hard `Uri transform` tertiary is an emote
unlock, not an item; it is exported with `"unlock": "emote"` and no `item_id`. Any
other unresolved name still fails.

Hard's mega-rare table lists Super attack(4), Super strength(4) and Super
defence(4) each at the outcome's 1/16,250. A shared footnote says they are always
received together. Counting them as three outcomes would make the pool sum to
8126/8125. The exporter folds rows that share a named footnote saying "together
with" into one entry, `{"items": [...], "section", "rarity_raw", "weight"}`. It
fails if the members, the names in the footnote or their rates disagree. This entry
has no top-level `item_id`, so a roller that does not support `items` rejects the
hard table instead of silently granting one potion.

# Challenge-scroll answers

`challenge-scrolls.wikitext` is the raw source of
[Treasure Trails/Guide/Challenge scrolls](https://oldschool.runescape.wiki/w/Treasure_Trails/Guide/Challenge_scrolls),
revision 15285563 (2 August 2026 04:01:28 UTC), fetched on 23 October 2026. SHA-256:
`20600907a4835352edf8a0f0f6e7415772ef5681c0731e752d1b8b3ad0fbcdb7`. It has 78
solutions: 44 medium, 22 hard and 12 elite.

`challenge-questions-cache.json` is the reviewed fixture of the cache's 90
`cluehelper_challenge_question` rows. It was extracted read-only from cache
`osrs-241_2026-10-20` (revision 241) with `dump-challenge-questions.cjs <tsps>/server`.
Two extractions were byte-identical. SHA-256:
`77327b32822954af062de2ededed0b07c1a06b92d65e6da264884f1966c2b3fc`. Each row's
`question` column holds (text, answer) pairs, so the cache has its own answers too.
Father Aereck and the Zoo keeper have two state-dependent pairs.

`clue_challenges.py` matches each cache row to the one Wiki solution that asks the
same question. It matches on the question text, not the name: cipher rows such as
`..._cipher_medium_0` and `..._medium_cryptic_vm02` (Teicuh) carry no NPC name, and
Nieve and Steve share one row. Every key must resolve, and every Wiki solution is
reached by at least one key. The Wiki answer, plus its `alternates` parsed from the
row's note, must equal the cache's answers. The one reviewed exception is Old crone:
the Wiki says 619, on both this page and her own page, and the cache says 623. The
export keeps the Wiki's 619, adds `cache_answers: [623]` and lists the disagreement in
`meta.cache_disagreements`. Which one the game accepts has not been verified.

Regenerate with `python -m scripts.drops.clue_challenges --out <path>`. Never
hand-edit the generated JSON.
