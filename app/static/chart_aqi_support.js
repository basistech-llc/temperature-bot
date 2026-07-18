// chart_aqi_support.js - Air Quality chart only (standalone page)

let aqiChart = null;
let aqiData = [];
let currentStart = null;
let currentEnd = null;
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

function formatTime(ts) {
  const date = new Date(ts);
  const isDayView =
    currentStart && currentEnd && currentEnd - currentStart <= 24 * 60 * 60;

  if (isDayView) {
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZoneName: "short",
    }).format(date);
  } else {
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZoneName: "short",
    }).format(date);
  }
}

function clearTemporalButtonSelection() {
  const temporalButtons = document.querySelectorAll(".temporal-buttons button");
  temporalButtons.forEach((button) => button.classList.remove("selected"));
}

function setTemporalButtonSelection(buttonId) {
  clearTemporalButtonSelection();
  const button = document.getElementById(buttonId);
  if (button) button.classList.add("selected");
}

function setPickersFromRange() {
  if (currentStart && currentEnd) {
    const sd = new Date(currentStart * 1000);
    const ed = new Date(currentEnd * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    const toISODate = (d) =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    document.getElementById("startDate").value = toISODate(sd);
    document.getElementById("endDate").value = toISODate(ed);
  }
  loadAirQualityData();
}

function pickersChanged() {
  const sd = document.getElementById("startDate").value;
  const ed = document.getElementById("endDate").value;
  if (sd) {
    const s = new Date(sd + "T00:00:00");
    currentStart = Math.floor(s.getTime() / 1000);
  }
  if (ed) {
    const e = new Date(ed + "T23:59:59");
    currentEnd = Math.floor(e.getTime() / 1000);
  }
  clearTemporalButtonSelection();
  loadAirQualityData();
}

function setTimePrevDays(days) {
  currentEnd = Math.floor(Date.now() / 1000);
  currentStart = currentEnd - days * 24 * 60 * 60;
  setPickersFromRange();
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

function setupEventListeners() {
  document.getElementById("dayBtn").addEventListener("click", () => {
    setTemporalButtonSelection("dayBtn");
    setTimePrevDays(1);
  });
  document.getElementById("weekBtn").addEventListener("click", () => {
    setTemporalButtonSelection("weekBtn");
    setTimePrevDays(7);
  });
  document.getElementById("monthBtn").addEventListener("click", () => {
    setTemporalButtonSelection("monthBtn");
    setTimePrevDays(31);
  });
  document.getElementById("allBtn").addEventListener("click", () => {
    setTemporalButtonSelection("allBtn");
    currentStart = null;
    currentEnd = null;
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    loadAirQualityData();
  });
  document
    .getElementById("startDate")
    .addEventListener("change", pickersChanged);
  document.getElementById("endDate").addEventListener("change", pickersChanged);
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
  module.exports = { airQualityAxisLayout, selectedLegendState };
}
