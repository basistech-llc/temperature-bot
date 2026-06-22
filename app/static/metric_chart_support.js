// metric_chart_support.js - Generic per-metric time-series chart
//
// Driven by window.METRIC_CHART_CONFIG (injected by metric_chart.html):
//   { metric, label, unit, decimals, yAxisLabel, title }
//
// Radon is special-cased: values are stored in Bq/m³ but the y-axis / tooltip
// are rendered in pCi/L whenever the user's site-wide temperature preference
// is Fahrenheit, using the same convention as the main page's radon cells.

let metricChart = null;
let metricData = [];
let preSelectedDeviceIds = [];

const METRIC_ENDPOINT = "/api/v1/metric";

function metricConfig() {
  return window.METRIC_CHART_CONFIG || {};
}

function metricDataUrl(cfg, start, end, deviceIds) {
  const params = new URLSearchParams();
  params.append("metric", cfg.metric);
  if (start !== null && start !== undefined) params.append("start", start);
  if (end !== null && end !== undefined) params.append("end", end);
  if (deviceIds && deviceIds.length > 0) {
    params.append("device_ids", deviceIds.join(","));
  }
  return `${METRIC_ENDPOINT}?${params.toString()}`;
}

function isRadon() {
  return metricConfig().metric === "radon";
}

function currentUnit() {
  const cfg = metricConfig();
  if (isRadon() && typeof TemperatureUtils !== "undefined") {
    return TemperatureUtils.getRadonUnit();
  }
  return cfg.unit || "";
}

function currentYAxisLabel() {
  if (isRadon()) {
    return `Radon (${currentUnit()})`;
  }
  return metricConfig().yAxisLabel || "";
}

function transformValue(v) {
  if (isRadon() && typeof TemperatureUtils !== "undefined") {
    // Reuse the main-page radon formatter so units stay in lockstep.
    return parseFloat(TemperatureUtils.formatRadon(v));
  }
  return v;
}

function currentDecimals() {
  const cfg = metricConfig();
  // pCi/L values are small (typical 0-4); show one decimal. Bq/m³ is integer.
  if (isRadon() && currentUnit() === "pCi/L") return 1;
  return typeof cfg.decimals === "number" ? cfg.decimals : 1;
}

function updateMetricRecordCount() {
  let totalRecords = 0;
  metricData.forEach((series) => {
    totalRecords += series.data.length;
  });
  const el = document.getElementById("metric-record-count");
  if (el) {
    el.textContent = `Total ${metricConfig().label || "metric"} datapoints: ${totalRecords}`;
  }
}

function loadMetricData() {
  const cfg = metricConfig();
  const url = metricDataUrl(
    cfg,
    currentStart,
    currentEnd,
    preSelectedDeviceIds,
  );

  console.log("Fetch metric ", url);
  return fetch(url)
    .then((response) => response.json())
    .then((json) => {
      metricData = json.series || [];
      createMetricSensorCheckboxes();
      updateMetricRecordCount();
      updateMetricChart();
    });
}

function createMetricSensorCheckboxes() {
  allSensors = metricData
    .map((series) => ({
      device_id: series.device_id,
      displayName: series.name,
      fullName: series.name,
      exclusionKey: series.device_id,
    }))
    .sort((a, b) =>
      a.displayName.localeCompare(b.displayName, undefined, {
        sensitivity: "base",
      }),
    );

  if (preSelectedDeviceIds.length > 0) {
    excludedSensorNames = new Set(
      allSensors
        .filter((s) => !preSelectedDeviceIds.includes(s.device_id))
        .map((s) => s.exclusionKey),
    );
  }

  renderSensorCheckboxes(null, updateMetricChart);
}

function updateMetricChart() {
  if (!metricChart) return;

  const cfg = metricConfig();
  const checkboxes = document.querySelectorAll(
    "#checkboxes input[type=checkbox]",
  );
  const dataMap = new Map(metricData.map((s) => [s.device_id, s]));

  const {
    series,
    legendSelected,
    markLines,
    yAxisMin,
    yAxisMax,
  } = buildSeriesAndAxis(checkboxes, allSensors, dataMap, transformValue, {
    dataKey: "device_id",
  });

  const titleText = (() => {
    if (preSelectedDeviceIds.length === 1) {
      const s = metricData.find(
        (d) => d.device_id === preSelectedDeviceIds[0],
      );
      if (s) return `${cfg.title} - ${s.name}`;
    }
    if (preSelectedDeviceIds.length > 1) {
      return `${cfg.title} - Multiple Devices`;
    }
    return cfg.title || "";
  })();

  const option = {
    title: { text: titleText, top: 0 },
    tooltip: {
      trigger: "axis",
      formatter: function (params) {
        const ts = params[0].value[0];
        const decimals = currentDecimals();
        const unit = currentUnit();
        let output = `${formatTime(ts)}<br>`;
        for (const p of params) {
          const val = p.value[1];
          output += `${p.marker} ${p.seriesName}: ${val.toFixed(decimals)}${unit ? " " + unit : ""}<br>`;
        }
        return output;
      },
    },
    legend: {
      data: series.map((s) => s.name),
      top: 40,
      selectedMode: series.length <= 1 ? false : true,
      selected: legendSelected,
    },
    grid: { top: 200, left: 100, right: 100, bottom: 120 },
    xAxis: {
      type: "time",
      name: "Time",
      axisLabel: {
        rotate: 45,
        formatter: function (value) {
          return formatTime(value);
        },
      },
    },
    yAxis: {
      type: "value",
      name: currentYAxisLabel(),
      min: yAxisMin,
      max: yAxisMax,
    },
    series: series,
  };

  if (markLines.length > 0) {
    option.series.push({
      name: "Day Breaks",
      type: "line",
      showSymbol: false,
      showLine: false,
      data: [],
      markLine: {
        symbol: "none",
        data: markLines,
        lineStyle: {
          type: "dotted",
          color: "#bbb",
          width: 1,
        },
        label: { show: false },
      },
    });
  }

  metricChart.setOption(option, { notMerge: true });
}

function setupMetricEventListeners() {
  document.getElementById("dayBtn").addEventListener("click", () => {
    setTemporalButtonSelection("dayBtn");
    setTimePrevDays(1);
    loadMetricData();
  });

  document.getElementById("weekBtn").addEventListener("click", () => {
    setTemporalButtonSelection("weekBtn");
    setTimePrevDays(7);
    loadMetricData();
  });

  document.getElementById("monthBtn").addEventListener("click", () => {
    setTemporalButtonSelection("monthBtn");
    setTimePrevDays(31);
    loadMetricData();
  });

  document.getElementById("allBtn").addEventListener("click", () => {
    setTemporalButtonSelection("allBtn");
    currentStart = null;
    currentEnd = null;
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    loadMetricData();
  });

  document.getElementById("startDate").addEventListener("change", () => {
    pickersChanged();
    loadMetricData();
  });
  document.getElementById("endDate").addEventListener("change", () => {
    pickersChanged();
    loadMetricData();
  });

  const selectAllBtn = document.getElementById("selectAllBtn");
  const clearAllBtn = document.getElementById("clearAllBtn");

  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", function () {
      excludedSensorNames.clear();
      const checkboxes = document.querySelectorAll(
        "#checkboxes input[type=checkbox]",
      );
      checkboxes.forEach((checkbox) => {
        checkbox.checked = true;
      });
      updateMetricChart();
    });
  }

  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", function () {
      allSensors.forEach((sensor) =>
        excludedSensorNames.add(sensor.exclusionKey ?? sensor.displayName),
      );
      programmaticCheckboxUpdate = true;
      const checkboxes = document.querySelectorAll(
        "#checkboxes input[type=checkbox]",
      );
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      programmaticCheckboxUpdate = false;
      updateMetricChart();
    });
  }

  // Radon: re-render when the site-wide temperature-unit toggle flips, so the
  // y-axis label and tooltip unit track the Bq/m³ <-> pCi/L preference.
  if (isRadon()) {
    const toggle = document.getElementById("temp-unit-toggle");
    if (toggle) {
      toggle.addEventListener("change", () => {
        updateMetricChart();
      });
    }
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", async function () {
    const chartEl = document.getElementById("metric-chart");
    if (!chartEl) return;

    const urlParams = new URLSearchParams(window.location.search);
    const deviceIdsParam = urlParams.get("device_ids");
    if (deviceIdsParam) {
      preSelectedDeviceIds = deviceIdsParam
        .split(",")
        .map((id) => parseInt(id.trim(), 10))
        .filter((n) => !isNaN(n));
    }

    await loadAllSensors();

    setTimePrevDays(7);
    setTemporalButtonSelection("weekBtn");

    metricChart = echarts.init(chartEl);

    setupMetricEventListeners();

    loadMetricData();
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { metricDataUrl };
}
