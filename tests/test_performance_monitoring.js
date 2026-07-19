"use strict";

const assert = require("assert");
const {
  percentile,
  rollingPercentile,
} = require("../app/static/performance_monitoring.js");

assert.strictEqual(percentile([], 0.5), null);
assert.strictEqual(percentile([30, 10, 20], 0.5), 20);
assert.strictEqual(percentile([10, 20], 0.95), 19.5);

const samples = [
  { observed_at_ms: 3000, total_ms: 30 },
  { observed_at_ms: 1000, total_ms: 10 },
  { observed_at_ms: 2000, total_ms: 20 },
  { observed_at_ms: 4000, total_ms: null },
];
assert.deepStrictEqual(rollingPercentile(samples, "total_ms", 0.5, 2), [
  [1000, 10],
  [2000, 15],
  [3000, 25],
]);

console.log("performance_monitoring.js tests passed");
