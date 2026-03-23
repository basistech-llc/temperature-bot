// chart_aqi_support.js - Air Quality chart only (standalone page)

let aqiChart = null;
let aqiData = [];
let currentStart = null;
let currentEnd = null;
const AQI_ENDPOINT = "/api/v1/air_quality";

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

function updateAQChart() {
  if (!aqiChart) return;

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

  const yAxes = [
    {
      type: "value",
      name: "PM2.5 (µg/m³)",
      axisLabel: { formatter: (v) => `${v}` },
      position: "left",
      offset: 0,
    },
    {
      type: "value",
      name: "PM10 (µg/m³)",
      axisLabel: { formatter: (v) => `${v}` },
      position: "left",
      offset: 75,
    },
    {
      type: "value",
      name: "O₃ (ppb)",
      axisLabel: { formatter: (v) => `${v}` },
      position: "left",
      offset: 150,
    },
    {
      type: "value",
      name: "NO₂ (ppb)",
      axisLabel: { formatter: (v) => `${v}` },
      position: "right",
      offset: 0,
    },
    {
      type: "value",
      name: "CO (ppm)",
      axisLabel: { formatter: (v) => `${v}` },
      position: "right",
      offset: 75,
    },
    {
      type: "value",
      name: "AQI",
      axisLabel: { formatter: (v) => `${v}`, color: "#E65100" },
      nameTextStyle: { color: "#E65100", fontWeight: "bold" },
      position: "right",
      offset: 150,
    },
  ];

  yAxes.forEach((ax, i) => {
    ax.splitLine = { show: i === 0 };
  });

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
    legend: { top: 40 },
    grid: { top: 120, left: 80, right: 80, bottom: 80 },
    xAxis: { type: "time", axisLabel: { rotate: 45 } },
    yAxis: yAxes,
    series: series,
    axisPointer: { link: [{ xAxisIndex: "all" }], snap: true },
  };

  aqiChart.setOption(option, { notMerge: false });
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

document.addEventListener("DOMContentLoaded", function () {
  setTimePrevDays(7);
  setTemporalButtonSelection("weekBtn");

  aqiChart = echarts.init(document.getElementById("aqi-chart"));
  setupEventListeners();
  loadAirQualityData();
});
