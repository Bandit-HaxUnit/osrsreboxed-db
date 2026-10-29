"use strict";
// Read-only extraction of the cache's challenge-scroll rows from a built TSPS server:
//   node dump-challenge-questions.cjs <tsps>/server > challenge-questions-cache.json
// Each row's `question` column holds (text, answer) pairs; repeated pairs are
// state-dependent variants (Father Aereck's graveyard, the Ardougne Zoo).
const server = require("path").resolve(process.argv[2]);
process.chdir(server); // the server resolves its data relative to its own directory
const { Server } = require(server + "/dist/Server");
Server.installProductionPathResolver();
const { CachePipeline } = require(server + "/dist/game/cache/CachePipeline");
CachePipeline.initialize();
const { PluginManager } = require(server + "/dist/plugins/PluginManager");
const C = PluginManager.getCoreApi().CacheDefinitions;
const TABLE = "cluehelper_challenge_question";
const table = C.getDbTableId(TABLE);
const column = C.getDbColumn(table, "question");
const rows = C.getDbTableRows(table).map(row => {
  const values = row.column(column), variants = [];
  for (let i = 0; i < values.length; i += 2) variants.push({ question: values[i], answer: values[i + 1] });
  return { key: C.getDbRowName(row.id), variants };
});
const { name, revision } = CachePipeline.active;
process.stdout.write(JSON.stringify({ source: { cache: name, revision, table: TABLE }, rows }, null, 2) + "\n");
