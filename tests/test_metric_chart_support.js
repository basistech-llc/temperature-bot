/**
 * Node.js tests for metric_chart_support.js URL construction.
 * Run with: node tests/test_metric_chart_support.js
 */
const { metricDataUrl } = require("../app/static/metric_chart_support.js");

let passed = 0;
let failed = 0;

function check(label, actual, expected) {
  if (actual === expected) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got "${actual}", expected "${expected}"`);
  }
}

check(
  "clicked radon cell keeps selected device id",
  metricDataUrl({ metric: "radon" }, 1780886400, 1781567999, [7]),
  "/api/v1/metric?metric=radon&start=1780886400&end=1781567999&device_ids=7",
);

check(
  "multiple selected device ids are comma-separated",
  metricDataUrl({ metric: "co2" }, 1780886400, 1781567999, [7, 9]),
  "/api/v1/metric?metric=co2&start=1780886400&end=1781567999&device_ids=7%2C9",
);

check(
  "all-time view omits empty temporal bounds and device filter",
  metricDataUrl({ metric: "voc" }, null, null, []),
  "/api/v1/metric?metric=voc",
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
