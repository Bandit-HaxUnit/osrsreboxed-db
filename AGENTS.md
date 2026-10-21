# Agent instructions

Follow [CLAUDE.md](CLAUDE.md) for this repository's pipeline and export contracts.

Manual edits to generated JSON are strictly forbidden, including `npc-dialogues.json`,
its indexes/shards/minified exports and every other generated export. This also applies
to conflict resolution, one-off repairs and post-dump patches. Fix canonical authoring
inputs, parsers or dumpers, add a regression check, then regenerate. Repeated dumps from
the same inputs must match exactly. Disclose any remaining mismatch; do not mask it with
downstream overrides or allow the next dump to overwrite a fix.
