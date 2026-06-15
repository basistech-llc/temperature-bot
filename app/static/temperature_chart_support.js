// temperature_chart_support.js - Temperature chart wiring
//
// This file depends on globals and helpers defined in time_series_chart_core.js:
// - currentStart/currentEnd, allSensors, excludedSensorNames, programmaticCheckboxUpdate
// - STATUS_ENDPOINT, buildSeriesAndAxis, loadAllSensors,
//   clearTemporalButtonSelection, setTemporalButtonSelection,
//   setPickersFromRange, pickersChanged, setTimePrevDays, formatTime,
//   renderSensorCheckboxes.

let tempChart = null; // ECharts instance for temperature
let tempData = []; // series from /api/v1/temperature
let currentDeviceIds = []; // devices to load; [] means all
let preSelectedDeviceIds = []; // device IDs from URL ?device_ids=; pre-checks specific sensor(s)
let allDevices = []; // reserved for future use
let temperatureMode = "raw"; // raw device readings or calculated FCU room temps

const TEMP_ENDPOINT = "/api/v1/temperature";

/****************************************************************
 * Temperature data loading
 ****************************************************************/
function updateTempRecordCount() {
  let totalRecords = 0;
  tempData.forEach((series) => {
    totalRecords += series.data.length;
  });
  const recordCountElement = document.getElementById("record-count");
  if (recordCountElement) {
    recordCountElement.textContent = `Total temperature datapoints: ${totalRecords}`;
  }
}

function loadTempData() {
  let url = TEMP_ENDPOINT;
  const params = new URLSearchParams();

  if (currentDeviceIds.length > 0) {
    params.append("device_ids", currentDeviceIds.join(","));
  }
  params.append("mode", temperatureMode);
  params.append("start", currentStart);
  params.append("end", currentEnd);
  url += "?" + params.toString();

  console.log("Fetch temperature ", url);
  return fetch(url)
    .then((response) => response.json())
    .then((json) => {
      tempData = json.series || [];
      console.log("tempData=", tempData);

      createAllSensorCheckboxes();

      updateTempRecordCount();
      updateTempChart();
    });
}

/****************************************************************
 * Checkbox rendering (temperature-specific wrapper)
 ****************************************************************/
function createAllSensorCheckboxes() {
  // Build one sensor per series so each device_id gets its own line; sort by displayName then
  // fullName to match status list order. Use device_id for lookup/exclusion; fullName for legend.
  const sensorsFromTemp = tempData.map((series) => {
    const fromStatus = allSensorsFromStatus.find(
      (s) => s.device_id === series.device_id,
    );
    return {
      device_id: series.device_id,
      displayName: series.name,
      fullName: (fromStatus && fromStatus.fullName) || series.name,
      exclusionKey: series.device_id,
      legendLabel: (fromStatus && fromStatus.fullName) || series.name,
    };
  });
  allSensors = sensorsFromTemp.sort((a, b) => {
    const cmp = a.displayName.localeCompare(b.displayName, undefined, {
      sensitivity: "base",
    });
    return cmp !== 0
      ? cmp
      : (a.fullName || "").localeCompare(b.fullName || "", undefined, {
          sensitivity: "base",
        });
  });
  // If navigating from a per-unit link, pre-check only the specified device(s).
  if (preSelectedDeviceIds.length > 0) {
    excludedSensorNames = new Set(
      allSensors
        .filter((s) => !preSelectedDeviceIds.includes(s.device_id))
        .map((s) => s.exclusionKey),
    );
  }
  renderSensorCheckboxes(null, updateTempChart);
}

/****************************************************************
 * Chart rendering
 ****************************************************************/
function updateTempChart() {
  if (!tempChart) return;

  console.log("updateTempChart");
  const checkboxes = document.querySelectorAll(
    "#checkboxes input[type=checkbox]",
  );

  const tempDataMap = new Map(
    tempData.map((series) => [series.device_id, series]),
  );
  const {
    series,
    legendSelected,
    markLines,
    yAxisMin,
    yAxisMax,
  } = buildSeriesAndAxis(
    checkboxes,
    allSensors,
    tempDataMap,
    (val) =>
      TemperatureUtils.getTemperatureUnitPreference()
        ? TemperatureUtils.celsiusToFahrenheit(val)
        : val,
    { dataKey: "device_id", legendName: "fullName" },
  );

  const option = {
    title: {
      text: (() => {
        let baseTitle =
          preSelectedDeviceIds.length > 1
            ? `Temperature Time Series - Multiple Devices`
            : preSelectedDeviceIds.length === 1
              ? `Temperature Time Series - ${(() => {
                  const s = tempData.find(
                    (d) => d.device_id === preSelectedDeviceIds[0],
                  );
                  return s ? s.name : `Device ${preSelectedDeviceIds[0]}`;
                })()}`
              : "Temperature Time Series";

        if (
          currentStart &&
          currentEnd &&
          currentEnd - currentStart <= 24 * 60 * 60
        ) {
          const dayDate = new Date(currentStart * 1000);
          const dayStr = new Intl.DateTimeFormat(undefined, {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric",
          }).format(dayDate);
          baseTitle += ` - ${dayStr}`;
        }

        return baseTitle;
      })(),
      top: 0,
    },
    tooltip: {
      trigger: "axis",
      formatter: function (params) {
        const ts = params[0].value[0];
        let output = `${formatTime(ts)}<br>`;
        for (const p of params) {
          const tempValue = p.value[1];
          const unit = TemperatureUtils.getTemperatureUnit();
          output += `${p.marker} ${p.seriesName}: ${tempValue.toFixed(
            1,
          )}${unit}<br>`;
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
      name: `Temperature (${TemperatureUtils.getTemperatureUnit()})`,
      min: yAxisMin,
      max: yAxisMax,
      interval: TemperatureUtils.getTemperatureUnitPreference() ? 10 : 5,
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
  tempChart.setOption(option, { notMerge: true });

  tempChart.off("legendselectchanged");
  tempChart.on("legendselectchanged", function (params) {
    const checkboxes = document.querySelectorAll(
      "#checkboxes input[type=checkbox]",
    );
    checkboxes.forEach((cb, i) => {
      const sensor = allSensors[i];
      if (!sensor) return;
      const seriesLabel = sensor.legendLabel ?? sensor.fullName ?? sensor.displayName;
      if (seriesLabel === params.name) {
        cb.checked = params.selected[params.name];
      }
    });
  });
}

/****************************************************************
 * Controls & wiring
 ****************************************************************/
function setupTemperatureEventListeners() {
  document
    .querySelectorAll('input[name="temperature-mode"]')
    .forEach((radio) => {
      radio.addEventListener("change", () => {
        if (!radio.checked || radio.value === temperatureMode) {
          return;
        }
        temperatureMode = radio.value;
        currentDeviceIds = [];
        preSelectedDeviceIds = [];
        excludedSensorNames.clear();
        reloadData();
      });
    });

  // Temporal buttons
  const dayBtn = document.getElementById("dayBtn");
  const weekBtn = document.getElementById("weekBtn");
  const monthBtn = document.getElementById("monthBtn");
  const allBtn = document.getElementById("allBtn");

  if (dayBtn) {
    dayBtn.addEventListener("click", () => {
      setTemporalButtonSelection("dayBtn");
      setTimePrevDays(1);
      reloadData();
    });
  }
  if (weekBtn) {
    weekBtn.addEventListener("click", () => {
      setTemporalButtonSelection("weekBtn");
      setTimePrevDays(7);
      reloadData();
    });
  }
  if (monthBtn) {
    monthBtn.addEventListener("click", () => {
      setTemporalButtonSelection("monthBtn");
      setTimePrevDays(31);
      reloadData();
    });
  }
  if (allBtn) {
    allBtn.addEventListener("click", () => {
      setTemporalButtonSelection("allBtn");
      currentStart = null;
      currentEnd = null;
      const sd = document.getElementById("startDate");
      const ed = document.getElementById("endDate");
      if (sd) sd.value = "";
      if (ed) ed.value = "";
      reloadData();
    });
  }

  // Date pickers
  const sd = document.getElementById("startDate");
  const ed = document.getElementById("endDate");
  if (sd) sd.addEventListener("change", () => { pickersChanged(); reloadData(); });
  if (ed) ed.addEventListener("change", () => { pickersChanged(); reloadData(); });

  // CSV export
  const downloadBtn = document.getElementById("downloadCsv");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      const checkboxes = document.querySelectorAll(
        "#checkboxes input[type=checkbox]",
      );
      const visibleSeries = [];

      if (currentDeviceIds && currentDeviceIds.length > 0) {
        visibleSeries.push(...tempData);
      } else {
        const tempDataMap = new Map(
          tempData.map((s) => [s.device_id, s]),
        );
        checkboxes.forEach((cb, i) => {
          const sensor = allSensors[i];
          if (!sensor) return;
          const seriesData = tempDataMap.get(sensor.device_id);
          if (cb.checked && seriesData) {
            visibleSeries.push(seriesData);
          }
        });
      }

      if (visibleSeries.length === 0) {
        alert("No data to export");
        return;
      }

      const csvNames = visibleSeries.map(
        (s) => (allSensors.find((sens) => sens.device_id === s.device_id) || {}).fullName || s.name,
      );
      let csvContent = "data:text/csv;charset=utf-8,";
      csvContent += "Time," + csvNames.join(",") + "\n";

      const allTimestamps = new Set();
      visibleSeries.forEach((series) => {
        series.data.forEach(([ts]) => allTimestamps.add(ts));
      });

      const sortedTimestamps = Array.from(allTimestamps).sort((a, b) => a - b);

      sortedTimestamps.forEach((ts) => {
        const row = [formatTime(ts * 1000)];
        visibleSeries.forEach((series) => {
          const dataPoint = series.data.find(([t]) => t === ts);
          row.push(dataPoint ? dataPoint[1] : "");
        });
        csvContent += row.join(",") + "\n";
      });

      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", "temperature_data.csv");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  }

  // Checkbox controls (Select All / Clear All)
  const selectAllBtn = document.getElementById("selectAllBtn");
  const clearAllBtn = document.getElementById("clearAllBtn");

  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", () => {
      excludedSensorNames.clear();
      const checkboxes = document.querySelectorAll(
        "#checkboxes input[type=checkbox]",
      );
      checkboxes.forEach((checkbox) => {
        checkbox.checked = true;
      });
      updateTempChart();
    });
  }

  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", () => {
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
      updateTempChart();
    });
  }
}

function reloadData() {
  console.log("reloadData (temperature)");
  if (!tempChart) return Promise.resolve();
  return loadTempData();
}

// Initialise when DOM is ready on the temperature chart page.
document.addEventListener("DOMContentLoaded", async function () {
  const tempEl = document.getElementById("temp-chart");
  if (!tempEl) {
    // Not on the temperature chart page; helpers are still used by lighting.
    return;
  }

  // When navigating from a per-unit link, pre-check only that device's checkbox.
  const urlParams = new URLSearchParams(window.location.search);
  const modeParam = urlParams.get("mode");
  if (modeParam === "raw" || modeParam === "calculated") {
    temperatureMode = modeParam;
    const modeRadio = document.querySelector(
      `input[name="temperature-mode"][value="${temperatureMode}"]`,
    );
    if (modeRadio) {
      modeRadio.checked = true;
    }
  }
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

  tempChart = echarts.init(tempEl);

  setupTemperatureEventListeners();

  await reloadData();
});
