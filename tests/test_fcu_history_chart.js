"use strict";

const assert = require("assert");
const {
  categoricalStateData,
  combinedFcuSeries,
  fcuCsvSeries,
  FCU_FAN_SPEEDS,
  FCU_MODES,
} = require("../app/static/fcu_history_chart.js");

const history = {
  temperature_series: [
    { name: "Hickory - FCU inlet", data: [[100, 20], [200, 21]] },
    { name: "Hickory - Room Temp", data: [[100, 22], [200, null]] },
  ],
  states: [
    { timestamp: 100, mode: "COOL", fan_speed: "LOW" },
    { timestamp: 200, mode: "HEAT", fan_speed: "HIGH" },
  ],
};
const series = combinedFcuSeries(history);
assert.deepStrictEqual(series.map((item) => item.name), [
  "Hickory - FCU inlet",
  "Hickory - Room Temp",
  "FCU Mode",
  "FCU Fan",
]);
assert.strictEqual(series[1].connectNulls, false);
assert.deepStrictEqual(series[1].data[1], [200000, null]);
assert.deepStrictEqual(
  categoricalStateData(history.states, "mode", FCU_MODES),
  [[100000, 2], [200000, 1]],
);
assert.deepStrictEqual(
  categoricalStateData(history.states, "fan_speed", FCU_FAN_SPEEDS),
  [[100000, 1], [200000, 4]],
);

const csvSeries = fcuCsvSeries(history);
assert.deepStrictEqual(csvSeries.map((item) => item.name), [
  "Hickory - FCU inlet",
  "Hickory - Room Temp",
  "FCU Mode",
  "FCU Fan",
]);
assert.deepStrictEqual(csvSeries[0].data, [[100, 20], [200, 21]]);
assert.deepStrictEqual(csvSeries[2].data, [[100, "COOL"], [200, "HEAT"]]);
assert.deepStrictEqual(
  fcuCsvSeries({ states: [{ timestamp: 100, mode: "cool", fan_speed: null }] }),
  [{ name: "FCU Mode", data: [[100, "COOL"]] }],
);

console.log("fcu_history_chart tests passed");
