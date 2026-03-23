// lighting_chart_support.js - Lighting (illuminance) chart functionality

let lightingChart = null;
let lightingData = [];
let preSelectedDeviceIds = []; // device IDs from URL ?device_ids=; pre-checks specific sensor(s)

const LIGHTING_ENDPOINT = "/api/v1/lighting";

/****************************************************************
 *** Record count
 ****************************************************************/
function updateLightingRecordCount() {
  let totalRecords = 0;
  lightingData.forEach((series) => {
    totalRecords += series.data.length;
  });
  const el = document.getElementById("lighting-record-count");
  if (el) {
    el.textContent = `Total lighting datapoints: ${totalRecords}`;
  }
}

/****************************************************************
 *** Data loading
 ****************************************************************/
function loadLightingData() {
  let url = LIGHTING_ENDPOINT;
  const params = new URLSearchParams();

  params.append("start", currentStart);
  params.append("end", currentEnd);
  url += "?" + params.toString();

  console.log("Fetch lighting ", url);
  return fetch(url)
    .then((response) => response.json())
    .then((json) => {
      lightingData = json.series || [];
      console.log("lightingData=", lightingData);

      // Build / refresh checkboxes for all lighting sensors
      createLightingSensorCheckboxes();

      updateLightingRecordCount();
      updateLightingChart();
    });
}

/****************************************************************
 *** Checkbox rendering
 ****************************************************************/
function createLightingSensorCheckboxes() {
  // Build one sensor per lighting series, keyed by device_id to avoid name-mismatch
  // between the lighting API (which may use Hubitat labels) and the status API.
  allSensors = lightingData
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

  // If navigating from a per-unit link, pre-check only the specified device(s).
  if (preSelectedDeviceIds.length > 0) {
    excludedSensorNames = new Set(
      allSensors
        .filter((s) => !preSelectedDeviceIds.includes(s.device_id))
        .map((s) => s.exclusionKey),
    );
  }

  renderSensorCheckboxes(null, updateLightingChart);
}

/****************************************************************
 *** Chart rendering
 ****************************************************************/
function updateLightingChart() {
  if (!lightingChart) return;

  const checkboxes = document.querySelectorAll(
    "#checkboxes input[type=checkbox]",
  );
  const dataMap = new Map(lightingData.map((s) => [s.device_id, s]));

  const {
    series,
    legendSelected,
    markLines,
    yAxisMin,
    yAxisMax,
  } = buildSeriesAndAxis(checkboxes, allSensors, dataMap, (v) => v, {
    dataKey: "device_id",
  });

  const option = {
    title: {
      text: (() => {
        if (preSelectedDeviceIds.length === 1) {
          const s = lightingData.find(
            (d) => d.device_id === preSelectedDeviceIds[0],
          );
          if (s) return `Lighting Time Series - ${s.name}`;
        }
        if (preSelectedDeviceIds.length > 1) {
          return "Lighting Time Series - Multiple Devices";
        }
        return "Lighting Time Series";
      })(),
      top: 0,
    },
    tooltip: {
      trigger: "axis",
      formatter: function (params) {
        const ts = params[0].value[0];
        let output = `${formatTime(ts)}<br>`;
        for (const p of params) {
          const val = p.value[1];
          output += `${p.marker} ${p.seriesName}: ${val.toFixed(1)} lx<br>`;
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
      name: "Illuminance (lx)",
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

  lightingChart.setOption(option, { notMerge: true });
}

/****************************************************************
 *** Event wiring & initial load
 ****************************************************************/
function setupLightingEventListeners() {
  document.getElementById("dayBtn").addEventListener("click", () => {
    setTemporalButtonSelection("dayBtn");
    setTimePrevDays(1);
    reloadLightingData();
  });

  document.getElementById("weekBtn").addEventListener("click", () => {
    setTemporalButtonSelection("weekBtn");
    setTimePrevDays(7);
    reloadLightingData();
  });

  document.getElementById("monthBtn").addEventListener("click", () => {
    setTemporalButtonSelection("monthBtn");
    setTimePrevDays(31);
    reloadLightingData();
  });

  document.getElementById("allBtn").addEventListener("click", () => {
    setTemporalButtonSelection("allBtn");
    currentStart = null;
    currentEnd = null;
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    reloadLightingData();
  });

  document.getElementById("startDate").addEventListener("change", () => {
    pickersChanged();
    reloadLightingData();
  });
  document.getElementById("endDate").addEventListener("change", () => {
    pickersChanged();
    reloadLightingData();
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
      updateLightingChart();
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
      updateLightingChart();
    });
  }
}

function reloadLightingData() {
  console.log("reloadLightingData");
  return loadLightingData();
}

document.addEventListener("DOMContentLoaded", async function () {
  const chartEl = document.getElementById("lighting-chart");
  if (!chartEl) return;

  // When navigating from a per-unit link, pre-check only that device's checkbox.
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

  lightingChart = echarts.init(chartEl);

  setupLightingEventListeners();

  reloadLightingData();
});

