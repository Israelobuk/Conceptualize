import test from "node:test";
import assert from "node:assert/strict";
import { buildRepositoryTree, periodMetrics, filterActivity, activityBars } from "../lib/dashboard-data.ts";

const now = Date.parse("2026-09-26T12:00:00Z");
const trace = (days, tokens, latency) => ({id: String(days), operation: "pack", inputs: {paths:["src/auth.py"]}, client:"Codex", timestamp: new Date(now - days * 86400000).toISOString(), returned_tokens:tokens, latency_ms:latency, token_budget:8000});
test("date filters and comparisons use observed traces only", () => {
  const data = [trace(1, 200, 10), trace(2, 400, 30), trace(9, 100, 50)];
  const metrics = periodMetrics(data, "7", now);
  assert.equal(metrics.operations, 2);
  assert.equal(metrics.tokens, 600);
  assert.equal(metrics.averageSize, 300);
  assert.equal(metrics.averageLatency, 20);
  assert.equal(metrics.change.operations, 100);
  assert.equal(filterActivity(data, "7", "pack", "auth", now).length, 2);
  assert.equal(filterActivity(data, "7", "search", "", now).length, 0);
});
test("missing historical activity does not fabricate a percentage", () => {
  assert.equal(periodMetrics([trace(1, 200, 10)], "7", now).change.tokens, null);
});
test("repository folders count unique descendant files", () => {
  const root = buildRepositoryTree(["src/auth/session.ts", "src/auth/tokens.ts", "tests/auth.test.ts", "README.md", "README.md"]);
  assert.equal(root.count, 4);
  assert.equal(root.children.find(n=>n.name==="src").count, 2);
  assert.equal(root.children.find(n=>n.name==="tests").children[0].path, "tests/auth.test.ts");
});
test("metric bars contain only observed activity", () => {
  const bars = activityBars([trace(1,200,10)], "7", "tokens", now);
  assert.equal(bars.reduce((a,b)=>a+b,0),200);
  assert.ok(bars.some(v=>v===0));
});
