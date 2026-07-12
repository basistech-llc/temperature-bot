/**
 * Node.js tests for shared time-series chart gap handling.
 * Run with: node tests/test_time_series_chart_core.js
 */
const {
  buildSeriesAndAxis,
  CHART_GAP_BREAK_SECONDS,
  lineDataWithGapBreaks,
  shiftTimeWindow,
  timeWindowFromPercent,
  temperatureSeriesLabel,
  zoomTimeWindow,
} = require("../app/static/time_series_chart_core.js");

let passed = 0;
let failed = 0;

function check(label, actual, expected) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson === expectedJson) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got ${actualJson}, expected ${expectedJson}`);
  }
}

check("gap threshold is one hour", CHART_GAP_BREAK_SECONDS, 3600);

check(
  "normal twenty minute cadence stays connected",
  lineDataWithGapBreaks(
    [
      [0, 20],
      [1200, 21],
      [2400, 22],
    ],
    (v) => v,
  ),
  [
    [0, 20],
    [1200000, 21],
    [2400000, 22],
  ],
);

check(
  "exactly one hour stays connected",
  lineDataWithGapBreaks(
    [
      [0, 20],
      [3600, 21],
    ],
    (v) => v,
  ),
  [
    [0, 20],
    [3600000, 21],
  ],
);

check(
  "more than one hour gets null marker at midpoint",
  lineDataWithGapBreaks(
    [
      [0, 20],
      [3601, 21],
    ],
    (v) => v,
  ),
  [
    [0, 20],
    [1800500, null],
    [3601000, 21],
  ],
);

const axis = buildSeriesAndAxis(
  [{ checked: true }],
  [{ device_id: 32, displayName: "Area 51" }],
  new Map([
    [
      32,
      {
        data: [
          [0, 20],
          [1200, 21],
          [4801, 22],
        ],
      },
    ],
  ]),
  (v) => v,
  { dataKey: "device_id" },
);
check(
  "gap marker is present in built series",
  axis.series[0].data,
  [
    [0, 20],
    [1200000, 21],
    [3000500, null],
    [4801000, 22],
  ],
);
check("null gap marker does not pull y-axis to zero", axis.yAxisMin, 15);

check("shift window earlier", shiftTimeWindow(100, 200, -1), { start: 0, end: 100 });
check("shift window later", shiftTimeWindow(100, 200, 1), { start: 200, end: 300 });
check("zoom in around center", zoomTimeWindow(100, 250, 1 / 1.5), {
  start: 125,
  end: 225,
});
check("zoom out around center", zoomTimeWindow(100, 200, 1.5), {
  start: 75,
  end: 225,
});
check("selected middle half becomes window", timeWindowFromPercent(100, 300, 25, 75), {
  start: 150,
  end: 250,
});
check(
  "raw FCU temperature label identifies source",
  temperatureSeriesLabel("Area 51", "FCU", "raw"),
  "Area 51 (FCU)",
);
check(
  "calculated FCU temperature label remains room-oriented",
  temperatureSeriesLabel("Area 51", "FCU", "calculated"),
  "Area 51",
);
check(
  "raw sensor temperature label is unchanged",
  temperatureSeriesLabel("Area 51 Sensor", null, "raw"),
  "Area 51 Sensor",
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
