// chart_support.js - AQI and Temperature chart functionality

let tempChart = null; // temperature chart
let tempData = []; // original data from API
let aqiChart = null;
let aqiData = [];
let currentStart = null; // time_t
let currentEnd = null; // time_t
let currentDeviceIds = []; // current devices to load. [] means load them all
let allDevices = []; // all available devices for dropdown
let allSensors = []; // dynamically loaded list of all available sensors
let selectedTemporalButton = null; // currently selected temporal button
const TEMP_ENDPOINT = "/api/v1/temperature";
const AQI_ENDPOINT = "/api/v1/air_quality";
const STATUS_ENDPOINT = "/api/v1/status";

/****************************************************************
 *** Sensor list loading
 ****************************************************************/
async function loadAllSensors() {
  try {
    const response = await fetch(STATUS_ENDPOINT);
    const data = await response.json();

    // Extract device names from the status data
    allSensors = data.devices
      .map((device) => device.device_name)
      .filter((name) => name) // Remove any null/undefined names
      .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' })); // Sort alphabetically (case-insensitive)

    console.log("Loaded sensors:", allSensors);
    return allSensors;
  } catch (error) {
    console.error("Failed to load sensor list:", error);
    // Fallback to empty array if API fails
    allSensors = [];
    return allSensors;
  }
}

/****************************************************************
 *** Temporal button selection management
 ****************************************************************/
function clearTemporalButtonSelection() {
  // Remove selected class from all temporal buttons
  const temporalButtons = document.querySelectorAll(".temporal-buttons button");
  temporalButtons.forEach((button) => {
    button.classList.remove("selected");
  });
  selectedTemporalButton = null;
}

function setTemporalButtonSelection(buttonId) {
  // Clear previous selection
  clearTemporalButtonSelection();

  // Set new selection
  const button = document.getElementById(buttonId);
  if (button) {
    button.classList.add("selected");
    selectedTemporalButton = buttonId;
  }
}

/****************************************************************
 *** Date selection
 ****************************************************************/
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
  reloadData();
}

function pickersChanged() {
  const sd = document.getElementById("startDate").value; // yyyy-mm-dd
  const ed = document.getElementById("endDate").value;

  if (sd) {
    const s = new Date(sd + "T00:00:00");
    currentStart = Math.floor(s.getTime() / 1000);
  }
  if (ed) {
    const e = new Date(ed + "T23:59:59");
    currentEnd = Math.floor(e.getTime() / 1000);
  }

  // Clear temporal button selection when dates are manually changed
  clearTemporalButtonSelection();

  reloadData();
}

function setTimePrevDays(days) {
  currentEnd = Math.floor(Date.now() / 1000);
  currentStart = currentEnd - days * 24 * 60 * 60;
  setPickersFromRange();
}

// Format time intelligently based on time scale
function formatTime(ts) {
  const date = new Date(ts);
  const now = new Date();

  // Check if we're in day view (last 24 hours)
  const isDayView =
    currentStart && currentEnd && currentEnd - currentStart <= 24 * 60 * 60;

  if (isDayView) {
    // For day view, show only time (HH:mm) since all data is same day
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZoneName: "short",
    }).format(date);
  } else {
    // For longer periods, show day and time
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

// Update record count display
function updateTempRecordCount() {
  let totalRecords = 0;
  tempData.forEach((series) => {
    totalRecords += series.data.length;
  }); // count records in each series
  let recordCountElement = document.getElementById("record-count");
  if (recordCountElement) {
    recordCountElement.textContent = `Total temperature datapoints: ${totalRecords}`;
  } else {
    console.error("no element record-count");
  }
}

/****************************************************************/

// Load data from API with optional parameters
function loadTempData() {
  let url = TEMP_ENDPOINT;
  const params = new URLSearchParams();

  // Support single device or multiple devices
  if (currentDeviceIds.length > 0) {
    params.append("device_ids", currentDeviceIds.join(","));
  }
  params.append("start", currentStart);
  params.append("end", currentEnd);
  url += "?" + params.toString();

  console.log("Fetch ", url);
  fetch(url)
    .then((response) => response.json())
    .then((json) => {
      tempData = json.series;
      console.log("tempData=", tempData);

      // Expected shape (example):
      // [{name: "Sensor 1", data:[[ts,val],[ts2,val2],[ts3,val3]...]},
      // {name: "Sensor 2", data:[[ts,val],[ts2,val2],[ts3,val3]...]},... ]

      // Create/update checkboxes for all sensors if not filtering by device
      if (currentDeviceIds.length == 0) {
        createAllSensorCheckboxes();
      }

      // Update record count display
      updateTempRecordCount();
      updateTempChart();
    });
}

// Create checkboxes for all sensors, enabling/disabling based on data availability
function createAllSensorCheckboxes() {
  const checkboxContainer = document.getElementById("checkboxes");

  // Clear existing checkbox items
  const existingItems = checkboxContainer.querySelectorAll(".checkbox-item");
  existingItems.forEach((item) => item.remove());

  // Create checkbox items wrapper
  const checkboxItemsWrapper = document.createElement("div");
  checkboxItemsWrapper.style.display = "flex";
  checkboxItemsWrapper.style.flexWrap = "wrap";
  checkboxItemsWrapper.style.gap = "0.5em";

  // Create a map of available sensor names for quick lookup
  const availableSensors = new Set(tempData.map((series) => series.name));

  allSensors.forEach((sensorName, index) => {
    const id = `checkbox-${index}`;
    const wrapper = document.createElement("div");
    wrapper.className = "checkbox-item";

    // Add disabled class if sensor has no data
    const hasData = availableSensors.has(sensorName);
    if (!hasData) {
      wrapper.classList.add("disabled");
    }

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = id;
    checkbox.checked = hasData; // Only check sensors that have data
    checkbox.disabled = !hasData; // Disable sensors without data

    const label = document.createElement("label");
    label.htmlFor = id;
    label.innerText = sensorName;
    if (!hasData) {
      label.classList.add("disabled");
    }

    console.log(
      "creating checkbox for sensor:",
      sensorName,
      "hasData:",
      hasData,
    );

    checkbox.addEventListener("change", updateTempChart);
    wrapper.appendChild(checkbox);
    wrapper.appendChild(label);
    checkboxItemsWrapper.appendChild(wrapper);
  });

  // Insert checkbox items at the beginning (buttons are at the end)
  checkboxContainer.insertBefore(
    checkboxItemsWrapper,
    checkboxContainer.firstChild,
  );
}

function updateTempChart() {
  // Called when a checkbox changes or data changes
  console.log("updateTempChart");
  const checkboxes = document.querySelectorAll(
    "#checkboxes input[type=checkbox]",
  );
  const series = [];

  // Create a map of tempData by sensor name for quick lookup
  const tempDataMap = new Map(tempData.map((series) => [series.name, series]));

  // Include all series but control visibility via legend selection
  const legendSelected = {};
  checkboxes.forEach((cb, i) => {
    const sensorName = allSensors[i];
    const seriesData = tempDataMap.get(sensorName);

    // Only include series that have data and are checked
    if (seriesData && cb.checked) {
      series.push({
        name: sensorName,
        type: "line",
        showSymbol: false,
        data: seriesData.data.map(([ts, val]) => [
          ts * 1000,
          TemperatureUtils.getTemperatureUnitPreference()
            ? TemperatureUtils.celsiusToFahrenheit(val)
            : val,
        ]), // convert to ms and temperature unit
      });
    }
    legendSelected[sensorName] = cb.checked;
  });

  // --- Add vertical dotted lines for day breaks ---
  // Find min and max timestamps across all series
  let minTs = Infinity;
  let maxTs = -Infinity;
  series.forEach((s) => {
    s.data.forEach(([ts, _]) => {
      if (ts < minTs) minTs = ts;
      if (ts > maxTs) maxTs = ts;
    });
  });

  console.log("minTs=", minTs, "maxTs=", maxTs);

  // Generate day boundaries between min and max
  const markLines = [];
  if (minTs !== Infinity && maxTs !== -Infinity) {
    // Get start of first day (midnight)
    const firstDay = new Date(minTs);
    firstDay.setHours(0, 0, 0, 0);
    let currentDay = new Date(firstDay.getTime() + 86400000); // Start with next day

    // Add a line for each day boundary up to max timestamp
    while (currentDay.getTime() <= maxTs) {
      markLines.push({
        xAxis: currentDay.getTime(),
        lineStyle: {
          type: "dotted",
          color: "#bbb",
          width: 1,
        },
        label: { show: false },
      });
      currentDay.setTime(currentDay.getTime() + 86400000); // Add 24 hours
    }
  }
  // --- End vertical lines ---

  // Calculate smart Y-axis range based on data
  let minTemp = Infinity;
  let maxTemp = -Infinity;
  series.forEach((s) => {
    s.data.forEach(([ts, temp]) => {
      if (temp < minTemp) minTemp = temp;
      if (temp > maxTemp) maxTemp = temp;
    });
  });

  // Add padding to the range (10% on each side, minimum 5 degrees)
  const tempRange = maxTemp - minTemp;
  const padding = Math.max(tempRange * 0.1, 5);
  const rawMin = Math.max(0, minTemp - padding);
  const rawMax = maxTemp + padding;

  // Round to nice numbers appropriate for temperature ranges
  function roundToNiceNumber(value, isMin) {
    if (value <= 0) return 0;

    // For temperature ranges, use smaller increments
    // Round to nearest 5 degrees for values under 100, nearest 10 for values over 100
    let increment;
    if (value < 100) {
      increment = 5;
    } else {
      increment = 10;
    }

    if (isMin) {
      // Round down to nearest nice number
      return Math.floor(value / increment) * increment;
    } else {
      // Round up to nearest nice number
      return Math.ceil(value / increment) * increment;
    }
  }

  const yAxisMin = roundToNiceNumber(rawMin, true);
  const yAxisMax = roundToNiceNumber(rawMax, false);

  const option = {
    title: {
      text: (() => {
        let baseTitle =
          currentDeviceIds && currentDeviceIds.length > 1
            ? `Temperature Time Series - Multiple Devices`
            : currentDeviceIds && currentDeviceIds.length === 1
              ? `Temperature Time Series - Device ${currentDeviceIds[0]}`
              : "Temperature Time Series";

        // Add date to title for day view
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
          const tempValue = p.value[1]; // This is already converted based on USE_FAHRENHEIT
          const unit = TemperatureUtils.getTemperatureUnit();
          output += `${p.marker} ${p.seriesName}: ${tempValue.toFixed(1)}${unit}<br>`;
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
      interval: TemperatureUtils.getTemperatureUnitPreference() ? 10 : 5, // 10°F intervals for Fahrenheit, 5°C intervals for Celsius
    },
    series: series,
  };

  // Add markLine for day breaks if we have any
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

  // Listen to legend selection changes and sync with checkboxes
  tempChart.off("legendselectchanged"); // Remove old listener if exists
  tempChart.on("legendselectchanged", function (params) {
    const checkboxes = document.querySelectorAll(
      "#checkboxes input[type=checkbox]",
    );
    checkboxes.forEach((cb, i) => {
      const sensorName = allSensors[i];
      if (sensorName === params.name) {
        cb.checked = params.selected[params.name];
      }
    });
  });
}

/****************************************************************/
// Air Quality chart setup
// =======================

// Air Quality Display and Units
AQI_UNITS = {
  "PM2.5": "PM2.5 µg/m³",
  PM10: "PM10 µg/m³",
  O3: "O₃ ppb",
  NO2: "NO₂ ppb",
  CO: "CO ppm",
};

function loadAirQualityData() {
  let url = AQI_ENDPOINT;
  const params = new URLSearchParams();
  params.append("start", currentStart);
  params.append("end", currentEnd);
  url += "?" + params.toString();

  return fetch(url)
    .then((r) => r.json())
    .then((json) => {
      // Expected shape (example):
      // { pm25: [[ts,val],...], pm10: [...], o3: [...], no2: [...], co: [...], aqi: [...] }
      aqiData = json;
      updateAQChart();
    })
    .catch((err) => {
      console.error("Error loading air quality:", err);
      // Keep previous data if fetch fails
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

// ==========================
// Render the Air Quality chart
// ==========================
function updateAQChart() {
  if (!aqiChart) return;

  // Convert seconds->ms for ECharts time axis
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
      axisLabel: { formatter: (v) => `${v}` },
      position: "right",
      offset: 150,
    },
  ];

  // Make alternate axes not draw overlapping grid lines
  yAxes.forEach((ax, i) => {
    ax.splitLine = { show: i === 0 }; // keep one set
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
    axisPointer: {
      // helps link with temp chart
      link: [{ xAxisIndex: "all" }],
      snap: true,
    },
  };

  aqiChart.setOption(option, { notMerge: false });

  // Keep charts linked (crosshair/zoom)
  // try { echarts.connect([tempChart, aqiChart]); } catch(_) {}
}

/****************************************************************/

// Set up event listeners
function setupEventListeners() {
  // Temporal button handlers
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
    // Clear date range to show all available data
    currentStart = null;
    currentEnd = null;
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    reloadData();
  });

  // Date pickers
  document
    .getElementById("startDate")
    .addEventListener("change", pickersChanged);
  document.getElementById("endDate").addEventListener("change", pickersChanged);

  /****************************************************************
   *** CSV Export
   ****************************************************************/
  // CSV Export start
  document.getElementById("downloadCsv").addEventListener("click", () => {
    const checkboxes = document.querySelectorAll(
      "#checkboxes input[type=checkbox]",
    );
    const visibleSeries = [];

    if (currentDeviceIds) {
      visibleSeries.push(...tempData);
    } else {
      // Create a map of tempData by sensor name for quick lookup
      const tempDataMap = new Map(
        tempData.map((series) => [series.name, series]),
      );

      checkboxes.forEach((cb, i) => {
        const sensorName = allSensors[i];
        const seriesData = tempDataMap.get(sensorName);
        if (cb.checked && seriesData) {
          visibleSeries.push(seriesData);
        }
      });
    }

    if (visibleSeries.length === 0) {
      alert("No data to export");
      return;
    }

    // Create CSV content
    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Time," + visibleSeries.map((s) => s.name).join(",") + "\n";

    // Get all unique timestamps
    const allTimestamps = new Set();
    visibleSeries.forEach((series) => {
      series.data.forEach(([ts]) => allTimestamps.add(ts));
    });

    const sortedTimestamps = Array.from(allTimestamps).sort((a, b) => a - b);

    // Create rows
    sortedTimestamps.forEach((ts) => {
      const row = [formatTime(ts * 1000)];
      visibleSeries.forEach((series) => {
        const dataPoint = series.data.find(([t]) => t === ts);
        row.push(dataPoint ? dataPoint[1] : "");
      });
      csvContent += row.join(",") + "\n";
    });

    // Download the file
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "temperature_data.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  });

  /****************************************************************
   *** END OF CSV EXPORT
   ****************************************************************/
}

// ===============================
// Checkbox Controls (Select All/Clear All)
// ===============================
function setupCheckboxControls() {
  const selectAllBtn = document.getElementById("selectAllBtn");
  const clearAllBtn = document.getElementById("clearAllBtn");

  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", function () {
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
    clearAllBtn.addEventListener("click", function () {
      const checkboxes = document.querySelectorAll(
        "#checkboxes input[type=checkbox]",
      );
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      updateTempChart();
    });
  }
}

function reloadData() {
  // Reload both charts’ data with the shared range
  console.log("reloadData");
  Promise.all([loadTempData(), loadAirQualityData()]).then(() => {
    // When both updated, keep crosshair synced
    // try { echarts.connect([tempChart  aqiChart ]); } catch(_) {}
  });
}

// ===============================
// Default: last 7 days on load
// ===============================
// After your initial loadData() call completes, also load AQ, then fill pickers:
document.addEventListener("DOMContentLoaded", async function () {
  // Load sensor list first
  await loadAllSensors();

  setTimePrevDays(7); // Initialize to 1 week of date
  setTemporalButtonSelection("weekBtn"); // Set week button as selected by default to match initial 7-day range

  aqiChart = echarts.init(document.getElementById("aqi-chart")); // aqi chart
  tempChart = echarts.init(document.getElementById("temp-chart")); // // Temperature chart

  console.log("aqiChart=", aqiChart, "tempChart=", tempChart);

  // Set up event listeners
  setupEventListeners();
  setupCheckboxControls();

  reloadData();
  // Load both charts then set
  loadTempData();
});
