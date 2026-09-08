import assert from "node:assert/strict";
import { test } from "node:test";
import { concatHighlightRanges } from "./prefixHighlight.ts";

test("4420 highlights both country and area cells", () => {
  const spans = concatHighlightRanges("44", "20", "4420");
  assert.deepEqual(spans.country, { start: 0, end: 2 });
  assert.deepEqual(spans.area, { start: 0, end: 2 });
});

test("20 highlights only the area prefix", () => {
  const spans = concatHighlightRanges("44", "20", "20");
  assert.equal(spans.country, null);
  assert.deepEqual(spans.area, { start: 0, end: 2 });
});

test("London does not highlight prefixes", () => {
  const spans = concatHighlightRanges("44", "20", "London");
  assert.equal(spans.country, null);
  assert.equal(spans.area, null);
});
