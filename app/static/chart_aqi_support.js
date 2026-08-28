// chart_aqi_support.js - Air Quality chart wiring
//
// This file depends on globals and helpers defined in time_series_chart_core.js:
// - currentStart/currentEnd, formatTime, clearTemporalButtonSelection,
//   setTemporalButtonSelection, setPickersFromRange, pickersChanged,
//   setTimePrevDays, setupCsvDownload.

let aqiChart = null;
let aqiData = [];
const AQI_ENDPOINT = "/api/v1/air_quality";
const AIR_QUALITY_AXES = [
  { seriesName: "PM2.5", name: "PM2.5 (µg/m³)", position: "left" },
  { seriesName: "PM10", name: "PM10 (µg/m³)", position: "left" },
  { seriesName: "O₃", name: "O₃ (ppb)", position: "left" },
  { seriesName: "NO₂", name: "NO₂ (ppb)", position: "right" },
  { seriesName: "CO", name: "CO (ppm)", position: "right" },
  {
    seriesName: "AQI",
    name: "AQI",
    position: "right",
    color: "#E65100",
  },
];

function airQualityAxisLayout(selected = {}) {
  const isSelected = (seriesName) => selected[seriesName] !== false;
  const gridSeries = isSelected("AQI")
    ? "AQI"
    : AIR_QUALITY_AXES.find((axis) => isSelected(axis.seriesName))
        ?.seriesName;
  const sideCounts = { left: 0, right: 0 };

  const yAxes = AIR_QUALITY_AXES.map((definition) => {
    const show = isSelected(definition.seriesName);
    const offset = show ? sideCounts[definition.position]++ * 75 : 0;
    const color = definition.color;
    return {
      type: "value",
      name: definition.name,
      show,
      position: definition.position,
      offset,
      axisLine: { show: true, ...(color ? { lineStyle: { color } } : {}) },
      axisTick: { show: true },
      axisLabel: {
        formatter: (value) => `${value}`,
        ...(color ? { color } : {}),
      },
      ...(color
        ? { nameTextStyle: { color, fontWeight: "bold" } }
        : {}),
      splitLine: {
        show: show && definition.seriesName === gridSeries,
        lineStyle: { color: "#d9dde3", type: "solid" },
      },
    };
  });

  return {
    yAxes,
    grid: {
      top: 120,
      left: 80 + Math.max(0, sideCounts.left - 1) * 75,
      right: 80 + Math.max(0, sideCounts.right - 1) * 75,
      bottom: 120,
    },
  };
}

function selectedLegendState(currentOption, selectedOverride = null) {
  return selectedOverride || currentOption?.legend?.[0]?.selected || {};
}

function loadAirQualityData() {
  let url = AQI_ENDPOINT;
  const params = new URLSearchParams();
  params.append("start", currentStart);
  params.append("end", currentEnd);
  url += "?" + params.toString();

  fetch(url)
    .then((r) => r.json())
    .then((json) => {
      aqiData = json;
      updateAQChart();
    })
    .catch((err) => {
      console.error("Error loading air quality:", err);
      updateAQChart();
    });
}

function unitFor(name) {
  switch (name) {
    case "PM2.5":
    case "PM10":
      return " µg/m³";
    case "O₃":
    case "NO₂":
      return " ppb";
    case "CO":
      return " ppm";
    default:
      return "";
  }
}

function updateAQChart(selectedOverride = null) {
  if (!aqiChart) return;

  const selected = selectedLegendState(
    aqiChart.getOption(),
    selectedOverride,
  );

  const toMs = (arr) => (arr || []).map(([ts, v]) => [ts * 1000, v]);

  const series = [
    { name: "PM2.5", data: toMs(aqiData.pm25), unit: "µg/m³", yAxisIndex: 0 },
    { name: "PM10", data: toMs(aqiData.pm10), unit: "µg/m³", yAxisIndex: 1 },
    { name: "O₃", data: toMs(aqiData.o3), unit: "ppb", yAxisIndex: 2 },
    { name: "NO₂", data: toMs(aqiData.no2), unit: "ppb", yAxisIndex: 3 },
    { name: "CO", data: toMs(aqiData.co), unit: "ppm", yAxisIndex: 4 },
    { name: "AQI", data: toMs(aqiData.aqi), unit: "", yAxisIndex: 5 },
  ].map((s) => ({
    name: s.name,
    type: "line",
    showSymbol: false,
    encode: { x: 0, y: 1 },
    yAxisIndex: s.yAxisIndex,
    data: s.data,
    ...(s.name === "AQI"
      ? {
          lineStyle: { width: 3.5 },
          itemStyle: { color: "#E65100" },
          color: "#E65100",
          z: 10,
        }
      : { lineStyle: { width: 1.5 } }),
  }));

  const { yAxes, grid } = airQualityAxisLayout(selected);

  const option = {
    title: { text: "Air Quality (multi-axis)", top: 0 },
    tooltip: {
      trigger: "axis",
      formatter: (params) => {
        if (!params || !params.length) return "";
        const ts = params[0].value[0];
        const d = new Date(ts);
        const time = new Intl.DateTimeFormat(undefined, {
          weekday: "short",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
          timeZoneName: "short",
        }).format(d);
        return params.reduce((out, p) => {
          return (
            out +
            `${p.marker} ${p.seriesName}: ${p.value[1]}${unitFor(p.seriesName)}<br>`
          );
        }, `${time}<br>`);
      },
    },
    legend: { top: 40, selected },
    grid,
    xAxis: {
      type: "time",
      axisLabel: {
        rotate: 45,
        formatter: function (value) {
          return formatTime(value);
        },
      },
    },
    yAxis: yAxes,
    series: series,
    axisPointer: { link: [{ xAxisIndex: "all" }], snap: true },
  };

  // Axis visibility and offsets depend on the selected legend entries. Replace
  // the option so ECharts does not retain axis properties from the prior
  // selection.
  aqiChart.setOption(option, { notMerge: true });
}

// Legend name and aqiData key for each exportable series, in display order.
const AQI_CSV_SERIES = [
  ["PM2.5", "pm25"],
  ["PM10", "pm10"],
  ["O₃", "o3"],
  ["NO₂", "no2"],
  ["CO", "co"],
  ["AQI", "aqi"],
];

/**
 * Series to export as CSV: legend-visible series that have data, in the
 * shared { name, data: [[ts, value], ...] } shape (timestamps in seconds).
 */
function aqiSeriesForCsv(data, selected) {
  return AQI_CSV_SERIES.filter(([name]) => selected[name] !== false)
    .map(([name, key]) => ({ name, data: data[key] || [] }))
    .filter((series) => series.data.length > 0);
}

function setupEventListeners() {
  document.getElementById("dayBtn").addEventListener("click", () => {
    setTemporalButtonSelection("dayBtn");
    setTimePrevDays(1);
    loadAirQualityData();
  });
  document.getElementById("weekBtn").addEventListener("click", () => {
    setTemporalButtonSelection("weekBtn");
    setTimePrevDays(7);
    loadAirQualityData();
  });
  document.getElementById("monthBtn").addEventListener("click", () => {
    setTemporalButtonSelection("monthBtn");
    setTimePrevDays(31);
    loadAirQualityData();
  });
  document.getElementById("allBtn").addEventListener("click", () => {
    setTemporalButtonSelection("allBtn");
    currentStart = null;
    currentEnd = null;
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    loadAirQualityData();
  });
  document.getElementById("startDate").addEventListener("change", () => {
    pickersChanged();
    loadAirQualityData();
  });
  document.getElementById("endDate").addEventListener("change", () => {
    pickersChanged();
    loadAirQualityData();
  });

  // CSV export
  setupCsvDownload(() => {
    const selected = selectedLegendState(aqiChart ? aqiChart.getOption() : null);
    const visibleSeries = aqiSeriesForCsv(aqiData, selected);
    return {
      visibleSeries,
      names: visibleSeries.map((s) => s.name),
      filename: "air_quality_data.csv",
    };
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    setTimePrevDays(7);
    setTemporalButtonSelection("weekBtn");

    aqiChart = echarts.init(document.getElementById("aqi-chart"));
    aqiChart.on("legendselectchanged", (event) => {
      updateAQChart(event.selected);
    });
    setupEventListeners();
    loadAirQualityData();
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { airQualityAxisLayout, aqiSeriesForCsv, selectedLegendState };
}
