/**
 * Node.js tests for browser-side air-quality threshold coloring.
 * Run with: node tests/test_air_quality_thresholds.js
 */
const thresholds = require("../app/static/air_quality_thresholds.json");
const {
  airQualityClassForValue,
  applyAirQualityClassWithThresholds,
} = require("../app/static/air_quality_coloring.js");

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

function fakeCell(metric, value) {
  const classes = new Set(["unrelated", "air-good", "air-fair"]);
  return {
    classes,
    textContent: value,
    getAttribute: (name) => {
      if (name === "data-air-quality-metric") return metric;
      if (name === "data-air-quality-value") return value;
      return null;
    },
    classList: {
      add: (name) => classes.add(name),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
    },
  };
}

check("CO2 equal fair threshold is good", airQualityClassForValue("co2", 600, thresholds), "air-good");
check("CO2 above fair threshold is fair", airQualityClassForValue("co2", 601, thresholds), "air-fair");
check("CO2 above poor threshold is poor", airQualityClassForValue("co2", 1001, thresholds), "air-poor");
check("humidity below poorBelow is poor", airQualityClassForValue("humidity", 29.9, thresholds), "air-poor");
check("humidity equal poorBelow is good", airQualityClassForValue("humidity", 30, thresholds), "air-good");
check("humidity above fair threshold is fair", airQualityClassForValue("humidity", 51, thresholds), "air-fair");
check("humidity above poor threshold is poor", airQualityClassForValue("humidity", 61, thresholds), "air-poor");
check("PM2.5 AQI moderate starts fair", airQualityClassForValue("pm25", 9.1, thresholds), "air-fair");
check("PM2.5 AQI USG starts poor", airQualityClassForValue("pm25", 35.5, thresholds), "air-poor");
check("unconfigured metric has no class", airQualityClassForValue("illuminance", 500, thresholds), "");

const cell = fakeCell("voc", "2001");
check("apply returns class", applyAirQualityClassWithThresholds(cell, thresholds), "air-poor");
check("apply removes old good class", cell.classes.has("air-good"), false);
check("apply removes old fair class", cell.classes.has("air-fair"), false);
check("apply keeps unrelated class", cell.classes.has("unrelated"), true);
check("apply adds poor class", cell.classes.has("air-poor"), true);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
