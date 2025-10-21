// chart_support.js - AQI and Temperature chart functionality

let tempChart = null; // temperature chart
let tempData = []; // original data from API
let aqiChart = null;
let aqiData = [];
let currentStart = null; // time_t
let currentEnd = null; // time_t
let currentDeviceIds = []; // current devices to load. [] means load them all
let allDevices = []; // all available devices for dropdown
const TEMP_ENDPOINT = "/api/v1/temperature";
const AQI_ENDPOINT = "/api/v1/air_quality";

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
    }).format(date);
  } else {
    // For longer periods, show day and time
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
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

      // Draw checkboxes if not filtering by device.
      // This causes all devices to be shown
      if (currentDeviceIds.length == 0) {
        const checkboxContainer = document.getElementById("checkboxes");
        checkboxContainer.innerHTML = "";
        tempData.forEach((series, index) => {
          const id = `checkbox-${index}`;
          const wrapper = document.createElement("span");
          wrapper.style.whiteSpace = "nowrap"; // keep label on one line with its checkbox
          wrapper.style.marginRight = "1em"; // small gap before next checkbox group

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.id = id;
          checkbox.checked = true;

          const label = document.createElement("label");
          label.htmlFor = id;
          label.innerText = series.name;

          console.log("creating checkbox for series ", series.name);

          checkbox.addEventListener("change", updateTempChart);
          wrapper.appendChild(checkbox);
          wrapper.appendChild(label);
          checkboxContainer.appendChild(wrapper);
        });
      }
      // Update record count display
      updateTempRecordCount();
      updateTempChart();
    });
}

function updateTempChart() {
  // Called when a checkbox changes or data changes
  console.log("updateTempChart");
  const checkboxes = document.querySelectorAll(
    "#checkboxes input[type=checkbox]",
  );
  const series = [];

  // Show only checked series
  checkboxes.forEach((cb, i) => {
    if (cb.checked) {
      series.push({
        name: tempData[i].name,
        type: "line",
        showSymbol: false,
        data: tempData[i].data.map(([ts, val]) => [
          ts * 1000,
          TemperatureUtils.getTemperatureUnitPreference()
            ? TemperatureUtils.celsiusToFahrenheit(val)
            : val,
        ]), // convert to ms and temperature unit
      });
    }
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
    },
    grid: { top: 200, left: 100, right: 100, bottom: 100 },
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
    setTimePrevDays(1);
  });

  document.getElementById("weekBtn").addEventListener("click", () => {
    setTimePrevDays(7);
  });

  document.getElementById("monthBtn").addEventListener("click", () => {
    setTimePrevDays(31);
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
      checkboxes.forEach((cb, i) => {
        if (cb.checked) {
          visibleSeries.push(tempData[i]);
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
document.addEventListener("DOMContentLoaded", function () {
  setTimePrevDays(7); // Initialize to 1 week of date
  aqiChart = echarts.init(document.getElementById("aqi-chart")); // aqi chart
  tempChart = echarts.init(document.getElementById("temp-chart")); // // Temperature chart

  console.log("aqiChart=", aqiChart, "tempChart=", tempChart);

  reloadData();
  // Load both charts then set
  loadTempData();

  // Set up event listeners
  setupEventListeners();
});
