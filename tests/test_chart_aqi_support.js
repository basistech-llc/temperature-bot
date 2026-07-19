/** Logic tests for selected-axis layout on the air-quality chart. */
const {
  airQualityAxisLayout,
  selectedLegendState,
} = require("../app/static/chart_aqi_support.js");

let passed = 0;
let failed = 0;

function check(label, condition) {
  if (condition) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}`);
  }
}

const aqiOnly = airQualityAxisLayout({
  "PM2.5": false,
  PM10: false,
  "O₃": false,
  "NO₂": false,
  CO: false,
  AQI: true,
});
const aqiAxis = aqiOnly.yAxes.find((axis) => axis.name === "AQI");

check("AQI axis remains visible", aqiAxis.show === true);
check("AQI scale is adjacent to plot", aqiAxis.offset === 0);
check("AQI tick values are numeric", aqiAxis.axisLabel.formatter(62) === "62");
check("AQI supplies horizontal rules", aqiAxis.splitLine.show === true);
check("deselected PM2.5 axis is hidden", aqiOnly.yAxes[0].show === false);
check("single right axis uses compact margin", aqiOnly.grid.right === 80);

const withoutAqi = airQualityAxisLayout({ AQI: false });
check(
  "first selected pollutant supplies rules when AQI is hidden",
  withoutAqi.yAxes[0].splitLine.show === true,
);
check(
  "hidden AQI does not supply rules",
  withoutAqi.yAxes[5].splitLine.show === false,
);

const allAxes = airQualityAxisLayout();
check("all left axes reserve margin", allAxes.grid.left === 230);
check("all right axes reserve margin", allAxes.grid.right === 230);
check("outer AQI axis uses third offset", allAxes.yAxes[5].offset === 150);
check(
  "first render tolerates an undefined ECharts option",
  Object.keys(selectedLegendState(undefined)).length === 0,
);
check(
  "legend event selection overrides the current option",
  selectedLegendState(undefined, { AQI: true }).AQI === true,
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
