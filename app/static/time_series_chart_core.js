// time_series_chart_core.js
// Shared helpers and state for time-series charts (temperature, lighting, etc.)

// Shared temporal window for all time-series pages.
let currentStart = null; // time_t (seconds)
let currentEnd = null; // time_t (seconds)

// Sensor metadata from /api/v1/status. Each entry: { displayName, fullName, device_id }.
let allSensors = [];
// Copy of allSensors from status load; used by temperature chart to resolve fullName when
// building from tempData.
let allSensorsFromStatus = [];
let selectedTemporalButton = null;

// Sensors the user has unchecked (excluded). Session-scoped.
let excludedSensorNames = new Set();

// When true, checkbox state is being set programmatically; do not update the
// exclusion set in change handlers.
let programmaticCheckboxUpdate = false;

const STATUS_ENDPOINT = "/api/v1/status";
const CHART_GAP_BREAK_SECONDS = 60 * 60;

function shiftTimeWindow(start, end, direction) {
  const width = end - start;
  const offset = direction * width;
  return { start: start + offset, end: end + offset };
}

function zoomTimeWindow(start, end, durationFactor) {
  const center = (start + end) / 2;
  const halfWidth = ((end - start) * durationFactor) / 2;
  return {
    start: Math.floor(center - halfWidth),
    end: Math.ceil(center + halfWidth),
  };
}

function timeWindowFromPercent(start, end, startPercent, endPercent) {
  const width = end - start;
  return {
    start: Math.floor(start + (width * startPercent) / 100),
    end: Math.ceil(start + (width * endPercent) / 100),
  };
}

function timeExtentForSeries(seriesList) {
  let minTimestamp = Infinity;
  let maxTimestamp = -Infinity;
  let timestampCount = 0;
  seriesList.forEach((series) => {
    series.data.forEach(([timestamp]) => {
      if (!isFiniteNumber(timestamp)) return;
      minTimestamp = Math.min(minTimestamp, timestamp);
      maxTimestamp = Math.max(maxTimestamp, timestamp);
      timestampCount += 1;
    });
  });
  return timestampCount >= 2 && minTimestamp < maxTimestamp
    ? { start: minTimestamp, end: maxTimestamp }
    : null;
}

function temperatureSeriesLabel(label, deviceType, mode) {
  return mode === "raw" && deviceType === "FCU" ? `${label} (FCU)` : label;
}

function buildSensor(displayName, deviceName, deviceId, deviceType) {
  const safeDisplay = displayName || deviceName || "";
  const fullName = deviceName || displayName || "";
  if (!safeDisplay) return null;
  return {
    displayName: safeDisplay,
    fullName,
    device_id: deviceId,
    deviceType,
  };
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function lineDataWithGapBreaks(data, valueTransform) {
  const lineData = [];
  let previousTs = null;

  data.forEach(([ts, val]) => {
    if (isFiniteNumber(ts) && previousTs !== null) {
      const delta = ts - previousTs;
      if (delta > CHART_GAP_BREAK_SECONDS) {
        lineData.push([(previousTs + delta / 2) * 1000, null]);
      }
    }
    lineData.push([
      ts * 1000,
      val === null || val === undefined ? null : valueTransform(val),
    ]);
    if (isFiniteNumber(ts)) {
      previousTs = ts;
    }
  });

  return lineData;
}

/****************************************************************
 * Shared helpers for time-series charts
 ****************************************************************/

/**
 * Build series, legend selection state, vertical day-break lines, and a
 * "nice" Y-axis range for a time-series chart.
 *
 * @param {NodeListOf<HTMLInputElement>} checkboxes
 * @param {Array<{displayName: string, fullName?: string, device_id?: number}>} sensors
 * @param {Map<string|number, {name?: string, data: Array<[number, number]>}>} dataMap - keyed
 *   by dataKey (e.g. displayName or device_id)
 * @param {(value: number) => number} valueTransform
 * @param {{ dataKey?: string, legendName?: string }} [options] - dataKey: sensor property for
 *   dataMap lookup (default 'displayName'); legendName: sensor property for series/legend label
 */
function buildSeriesAndAxis(checkboxes, sensors, dataMap, valueTransform, options) {
  const dataKey = (options && options.dataKey) || "displayName";
  const legendName = (options && options.legendName) || "displayName";
  const series = [];
  const legendSelected = {};

  checkboxes.forEach((cb, i) => {
    const sensor = sensors[i];
    if (!sensor) return;
    const key = sensor[dataKey];
    const label = sensor[legendName] || sensor.displayName;
    const seriesData = dataMap.get(key);

    if (seriesData && cb.checked) {
      series.push({
        name: label,
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: lineDataWithGapBreaks(seriesData.data, valueTransform),
      });
    }
    legendSelected[label] = cb.checked;
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
      if (!isFiniteNumber(val)) return;
      if (val < minVal) minVal = val;
      if (val > maxVal) maxVal = val;
    });
  });

  if (minVal === Infinity || maxVal === -Infinity) {
    return { series, legendSelected, markLines, yAxisMin: 0, yAxisMax: 100 };
  }

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
      .map((device) =>
        buildSensor(
          device.display_name,
          device.device_name,
          device.device_id,
          device.device_type,
        ),
      )
      .filter((sensor) => sensor !== null)
      .sort((a, b) =>
        a.displayName.localeCompare(b.displayName, undefined, {
          sensitivity: "base",
        }),
      );
    allSensorsFromStatus = allSensors.slice();

    console.log("Loaded sensors:", allSensors);
    return allSensors;
  } catch (error) {
    console.error("Failed to load sensor list:", error);
    allSensors = [];
    allSensorsFromStatus = [];
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
/**
 * @param {string[]|null} availableNames - If null, render all allSensors without filtering
 *   (e.g. temperature chart builds allSensors from tempData). Otherwise filter to sensors
 *   whose displayName is in the set.
 */
function renderSensorCheckboxes(availableNames, onChange) {
  const checkboxContainer = document.getElementById("checkboxes");
  if (!checkboxContainer) return;

  const existingItems = checkboxContainer.querySelectorAll(".checkbox-item");
  existingItems.forEach((item) => item.remove());

  const checkboxItemsWrapper = document.createElement("div");
  checkboxItemsWrapper.style.display = "flex";
  checkboxItemsWrapper.style.flexWrap = "wrap";
  checkboxItemsWrapper.style.gap = "0.5em";

  const availableSensors =
    availableNames === null || availableNames === undefined
      ? null
      : new Set(availableNames);
  if (availableSensors !== null) {
    allSensors = allSensors.filter((sensor) =>
      availableSensors.has(sensor.displayName),
    );
  }

  programmaticCheckboxUpdate = true;
  allSensors.forEach((sensor, index) => {
    const sensorName = sensor.displayName;
    const fullName = sensor.fullName || sensorName;
    const exclusionKey = sensor.exclusionKey ?? sensor.displayName;
    const hasData = availableSensors === null || availableSensors.has(sensorName);
    const id = `checkbox-${index}`;
    const wrapper = document.createElement("div");
    wrapper.className = "checkbox-item";

    if (!hasData) {
      wrapper.classList.add("disabled");
    }

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = id;
    checkbox.checked = hasData && !excludedSensorNames.has(exclusionKey);
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
        excludedSensorNames.delete(exclusionKey);
      } else {
        excludedSensorNames.add(exclusionKey);
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

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    buildSeriesAndAxis,
    CHART_GAP_BREAK_SECONDS,
    lineDataWithGapBreaks,
    shiftTimeWindow,
    timeWindowFromPercent,
    timeExtentForSeries,
    temperatureSeriesLabel,
    zoomTimeWindow,
  };
}
