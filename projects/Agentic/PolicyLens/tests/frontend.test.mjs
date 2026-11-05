// Run with: node --test tests/frontend.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { renderParagraphs, duration, isRowKey } from "../web/js/rendering.js";
import { request } from "../web/js/api.js";

test("literal bracket numbers stay text while explicit citations become buttons", () => {
  const html = renderParagraphs({text:"unused", citations:[{number:1}],
    parts:[{text:"The policy literally says [1] and <script>.", citations:[1]}]});
  assert.ok(html.includes("says [1] and &lt;script&gt;"));
  assert.equal((html.match(/class="citation-marker"/g) || []).length, 1);
  assert.ok(!renderParagraphs({text:"Older text [1]",citations:[{number:1}]}).includes("<button"));
});

test("download-link keyboard actions are not intercepted", () => {
  assert.equal(Boolean(isRowKey({key:"Enter", target:{matches:()=>false}})), false);
  assert.equal(Boolean(isRowKey({key:"Enter", target:{matches:()=>true}})), true);
  assert.equal(Boolean(isRowKey({key:"Tab", target:{matches:()=>true}})), false);
});

test("missing/error latency is not shown as zero seconds", () => {
  assert.equal(duration(null), "—");
  assert.equal(duration(undefined), "—");
  assert.equal(duration(0), "0.00s");
});

test("non-JSON failures show a readable HTTP error", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response("<h1>Bad gateway</h1>", {status:502});
  try { await assert.rejects(request("/ask"), /HTTP 502/); }
  finally { globalThis.fetch = original; }
});
