// time_series_chart_core.js
// Shared helpers and state for time-series charts (temperature, lighting, etc.)

// Shared temporal window for all time-series pages.
let currentStart = null; // time_t (seconds)
let currentEnd = null; // time_t (seconds)

// Shared sensor metadata loaded from /api/v1/status.
// Each entry: { displayName, fullName }
let allSensors = [];
let selectedTemporalButton = null;

// Sensors the user has unchecked (excluded). Session-scoped.
let excludedSensorNames = new Set();

// When true, checkbox state is being set programmatically; do not update the
// exclusion set in change handlers.
let programmaticCheckboxUpdate = false;

const STATUS_ENDPOINT = "/api/v1/status";

function buildSensor(displayName, deviceName) {
  const safeDisplay = displayName || deviceName || "";
  const fullName = deviceName || displayName || "";
  if (!safeDisplay) return null;
  return {
    displayName: safeDisplay,
    fullName,
  };
}

/****************************************************************
 * Shared helpers for time-series charts
 ****************************************************************/

/**
 * Build series, legend selection state, vertical day-break lines, and a
 * "nice" Y-axis range for a time-series chart.
 *
 * @param {NodeListOf<HTMLInputElement>} checkboxes
 * @param {Array<{displayName: string}>} sensors
 * @param {Map<string, {name: string, data: Array<[number, number]>}>} dataMap
 * @param {(value: number) => number} valueTransform
 */
function buildSeriesAndAxis(checkboxes, sensors, dataMap, valueTransform) {
  const series = [];
  const legendSelected = {};

  checkboxes.forEach((cb, i) => {
    const sensor = sensors[i];
    if (!sensor) return;
    const sensorName = sensor.displayName;
    const seriesData = dataMap.get(sensorName);

    if (seriesData && cb.checked) {
      series.push({
        name: sensorName,
        type: "line",
        showSymbol: false,
        data: seriesData.data.map(([ts, val]) => [
          ts * 1000,
          valueTransform(val),
        ]),
      });
    }
    legendSelected[sensorName] = cb.checked;
  });

  // Vertical day-break lines
  let minTs = Infinity;
  let maxTs = -Infinity;
  series.forEach((s) => {
    s.data.forEach(([ts]) => {
      if (ts < minTs) minTs = ts;
      if (ts > maxTs) maxTs = ts;
    });
  });

  const markLines = [];
  if (minTs !== Infinity && maxTs !== -Infinity) {
    const firstDay = new Date(minTs);
    firstDay.setHours(0, 0, 0, 0);
    let currentDay = new Date(firstDay.getTime() + 86400000);
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
      currentDay.setTime(currentDay.getTime() + 86400000);
    }
  }

  // Y-axis range
  let minVal = Infinity;
  let maxVal = -Infinity;
  series.forEach((s) => {
    s.data.forEach(([, val]) => {
      if (val < minVal) minVal = val;
      if (val > maxVal) maxVal = val;
    });
  });

  const range = maxVal - minVal;
  const padding = Math.max(range * 0.1, 5);
  const rawMin = Math.max(0, minVal - padding);
  const rawMax = maxVal + padding;

  function roundToNiceNumber(value, isMin) {
    if (value <= 0) return 0;
    const increment = value < 100 ? 5 : 10;
    return isMin
      ? Math.floor(value / increment) * increment
      : Math.ceil(value / increment) * increment;
  }

  const yAxisMin = roundToNiceNumber(rawMin, true);
  const yAxisMax = roundToNiceNumber(rawMax, false);

  return { series, legendSelected, markLines, yAxisMin, yAxisMax };
}

/****************************************************************
 * Sensor list loading
 ****************************************************************/
async function loadAllSensors() {
  try {
    const response = await fetch(STATUS_ENDPOINT);
    const data = await response.json();

    allSensors = data.devices
      .map((device) => buildSensor(device.display_name, device.device_name))
      .filter((sensor) => sensor !== null)
      .sort((a, b) =>
        a.displayName.localeCompare(b.displayName, undefined, {
          sensitivity: "base",
        }),
      );

    console.log("Loaded sensors:", allSensors);
    return allSensors;
  } catch (error) {
    console.error("Failed to load sensor list:", error);
    allSensors = [];
    return allSensors;
  }
}

/****************************************************************
 * Temporal button & date helpers
 ****************************************************************/
function clearTemporalButtonSelection() {
  const temporalButtons = document.querySelectorAll(".temporal-buttons button");
  temporalButtons.forEach((button) => {
    button.classList.remove("selected");
  });
  selectedTemporalButton = null;
}

function setTemporalButtonSelection(buttonId) {
  clearTemporalButtonSelection();
  const button = document.getElementById(buttonId);
  if (button) {
    button.classList.add("selected");
    selectedTemporalButton = buttonId;
  }
}

function setPickersFromRange() {
  if (currentStart && currentEnd) {
    const sd = new Date(currentStart * 1000);
    const ed = new Date(currentEnd * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    const toISODate = (d) =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const sdInput = document.getElementById("startDate");
    const edInput = document.getElementById("endDate");
    if (sdInput) sdInput.value = toISODate(sd);
    if (edInput) edInput.value = toISODate(ed);
  }
  // The page-specific code is responsible for calling its own reload.
}

function pickersChanged() {
  const sdInput = document.getElementById("startDate");
  const edInput = document.getElementById("endDate");
  const sd = sdInput ? sdInput.value : "";
  const ed = edInput ? edInput.value : "";

  if (sd) {
    const s = new Date(sd + "T00:00:00");
    currentStart = Math.floor(s.getTime() / 1000);
  }
  if (ed) {
    const e = new Date(ed + "T23:59:59");
    currentEnd = Math.floor(e.getTime() / 1000);
  }

  clearTemporalButtonSelection();
  // Page-specific code decides how to reload.
}

function setTimePrevDays(days) {
  currentEnd = Math.floor(Date.now() / 1000);
  currentStart = currentEnd - days * 24 * 60 * 60;
  setPickersFromRange();
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

/****************************************************************
 * Generic checkbox rendering (shared)
 ****************************************************************/
function renderSensorCheckboxes(availableNames, onChange) {
  const checkboxContainer = document.getElementById("checkboxes");
  if (!checkboxContainer) return;

  const existingItems = checkboxContainer.querySelectorAll(".checkbox-item");
  existingItems.forEach((item) => item.remove());

  const checkboxItemsWrapper = document.createElement("div");
  checkboxItemsWrapper.style.display = "flex";
  checkboxItemsWrapper.style.flexWrap = "wrap";
  checkboxItemsWrapper.style.gap = "0.5em";

  const availableSensors = new Set(availableNames);
  allSensors = allSensors.filter((sensor) =>
    availableSensors.has(sensor.displayName),
  );

  programmaticCheckboxUpdate = true;
  allSensors.forEach((sensor, index) => {
    const sensorName = sensor.displayName;
    const fullName = sensor.fullName || sensorName;
    const id = `checkbox-${index}`;
    const wrapper = document.createElement("div");
    wrapper.className = "checkbox-item";

    const hasData = availableSensors.has(sensorName);
    if (!hasData) {
      wrapper.classList.add("disabled");
    }

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = id;
    checkbox.checked = hasData && !excludedSensorNames.has(sensorName);
    checkbox.disabled = !hasData;

    const label = document.createElement("label");
    label.htmlFor = id;
    label.innerText = sensorName;
    label.title = fullName;
    if (!hasData) {
      label.classList.add("disabled");
    }

    checkbox.addEventListener("change", () => {
      if (programmaticCheckboxUpdate) return;
      if (checkbox.checked) {
        excludedSensorNames.delete(sensorName);
      } else {
        excludedSensorNames.add(sensorName);
      }
      onChange();
    });

    wrapper.appendChild(checkbox);
    wrapper.appendChild(label);
    checkboxItemsWrapper.appendChild(wrapper);
  });

  programmaticCheckboxUpdate = false;

  checkboxContainer.insertBefore(
    checkboxItemsWrapper,
    checkboxContainer.firstChild,
  );
}

