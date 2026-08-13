"use strict";

const FCU_MODES = ["OFF", "HEAT", "COOL", "AUTO", "FAN", "DRY"];
const FCU_FAN_SPEEDS = ["AUTO", "LOW", "MID2", "MID1", "HIGH"];

function categoricalStateData(states, field, categories) {
  return (states || []).map((state) => [
    Number(state.timestamp) * 1000,
    state[field] == null ? null : categories.indexOf(String(state[field]).toUpperCase()),
  ]);
}

function combinedFcuSeries(history) {
  const temperatures = (history.temperature_series || []).map((series) => ({
    name: series.name,
    type: "line",
    showSymbol: false,
    connectNulls: false,
    yAxisIndex: 0,
    data: series.data.map(([timestamp, value]) => [timestamp * 1000, value]),
  }));
  return temperatures.concat([
    {
      name: "FCU Mode",
      type: "line",
      step: "end",
      showSymbol: false,
      connectNulls: false,
      yAxisIndex: 1,
      data: categoricalStateData(history.states, "mode", FCU_MODES),
    },
    {
      name: "FCU Fan",
      type: "line",
      step: "end",
      showSymbol: false,
      connectNulls: false,
      yAxisIndex: 2,
      data: categoricalStateData(history.states, "fan_speed", FCU_FAN_SPEEDS),
    },
  ]);
}

/**
 * Series to export as CSV, in the shared { name, data: [[ts, value], ...] }
 * shape (timestamps in seconds): temperature series with raw °C values, plus
 * FCU Mode and FCU Fan state as text columns.
 */
function fcuCsvSeries(history) {
  const stateSeries = (field, label) => ({
    name: label,
    data: (history.states || [])
      .filter((state) => state[field] != null)
      .map((state) => [
        Number(state.timestamp),
        String(state[field]).toUpperCase(),
      ]),
  });
  return (history.temperature_series || [])
    .map((series) => ({ name: series.name, data: series.data }))
    .concat([stateSeries("mode", "FCU Mode"), stateSeries("fan_speed", "FCU Fan")])
    .filter((series) => series.data.length > 0);
}

async function loadFcuHistory(request = fetch) {
  const page = document.getElementById("fcu-history-page");
  const deviceId = Number(page?.dataset.fcuDeviceId);
  if (!Number.isInteger(deviceId)) throw new Error("An FCU is required.");
  const response = await request(`/api/v1/fcu_history?fcu_device_id=${deviceId}`);
  const history = await response.json();
  if (!response.ok) throw new Error(history.error || "Unable to load FCU history.");
  const chart = echarts.init(document.getElementById("fcu-history-chart"));
  chart.setOption({
    title: { text: `${history.room_name}: FCU and Room History` },
    tooltip: { trigger: "axis" },
    legend: { top: 35 },
    grid: { top: 90, left: 80, right: 150, bottom: 80 },
    xAxis: { type: "time", name: "Time" },
    yAxis: [
      { type: "value", name: "Temperature (°C)", scale: true },
      { type: "category", name: "Mode", data: FCU_MODES, offset: 0 },
      { type: "category", name: "Fan", data: FCU_FAN_SPEEDS, offset: 70 },
    ],
    dataZoom: [{ type: "inside" }, { type: "slider" }],
    series: combinedFcuSeries(history),
  });
  window.addEventListener("resize", () => chart.resize());
  setupCsvDownload(() => {
    const visibleSeries = fcuCsvSeries(history);
    return {
      visibleSeries,
      names: visibleSeries.map((series) => series.name),
      filename: `fcu_${deviceId}_history.csv`,
    };
  });
  return history;
}

if (typeof window !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => {
    loadFcuHistory().catch((error) => {
      document.getElementById("fcu-history-message").textContent = error.message;
    });
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { categoricalStateData, combinedFcuSeries, fcuCsvSeries, FCU_FAN_SPEEDS, FCU_MODES };
}
