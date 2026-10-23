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
