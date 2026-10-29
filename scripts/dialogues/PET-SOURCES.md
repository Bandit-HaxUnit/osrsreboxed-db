# Pet transcript collection evidence

This change includes the Wiki's Pet dialogue category in the existing NPC transcript pipeline. The category API returned80 transcript pages on27October2026; a rendered category listing showing79 was stale. Original wikitext and revision IDs remain in the raw caches, and the authoring index retains each transcript's source revision and NPC identity provenance.

## Reproduction

- Run `python -m scripts.dialogues.update --offline` against the committed caches.
- The existing merged master + PR#9 raw-input baseline produces3,285 runtime records, semantically equal to the installed TSPS aggregate.
- Add only the80 Pet transcripts and their78 missing identity pages to that pinned raw baseline. No new transcript dependencies or footer templates were needed.
- Run the normal offline exporter. It produces3,365 runtime records; all3,285 old records remain deeply equal, and exactly80 Pet records are added.
- Existing NPC-index candidates are preserved. Twelve cat IDs gain an additional Cat candidate; consumers must select a Pet page deliberately rather than treating candidate order as a routing policy.
- Integration additionally links the15 previously unindexed kitten/overgrown/hellcat follower IDs to the two existing A Tail of Two Cats chore variants. Cache241 and the existing quest participant/selector establish these identities. This adds index availability only; it does not bypass ownership, catspeak, stage or native Interact routing in the consumer.
- Repeating the exporter with unchanged inputs produces byte-identical aggregate, minified data, index, type index, manifest,3,365 shards and three authoring/report outputs:3,373 files.

## Source types

`dialogue-types.json` classifies top-level `Transcript` declarations. It distinguishes Pet and item sources and ignores nested/commented declarations. Missing/conflicting declarations and authored-only corrected records remain `unclassified`. This additive index does not modify existing runtime record shapes and does not establish quest state, ownership or interaction eligibility.

## Limits

A fresh full online collection also discovers an unrelated General Montoya transcript. Its existing audited correction expects no source record and intentionally stops generation on the changed fingerprint. That authoring review is outside this Pet collection change; it was not bypassed or overwritten. The committed scoped raw inputs retain the pinned non-Pet baseline and the newly fetched official Pet pages. Offline reproduction is supported; an unrestricted fresh online generation still needs the Montoya correction reviewed separately.

Pet transcripts include conditional variants, item-use responses and Menagerie arena overheads. Importing them alone does not implement those gameplay paths. In particular Olmlet has six standard form sections plus six Menagerie overhead sections; Puppadile and Vespina preserve three and two random conversation alternatives respectively. Consumers must choose the actual physical form's section and keep the random nodes as random alternatives.

## Independent checks

An independent Codex reviewer traced collection, real cache writes, reference traversal, classification and generation. Their extra scenario promotes a Pet from an old quest/reference cache, refreshes its changed nested dependency, confirms the obsolete dependency is not followed, and repeats the fetch with identical file bytes. Only remote transport/category responses were substituted. They separately confirmed preservation of all baseline records/index candidates and ran133 targeted parser/export/identity/flow tests. Game lifecycle/rendering checks belong to the separate TSPS consumer PR.
