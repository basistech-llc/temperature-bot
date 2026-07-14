/* interactivity for unit speed grid
 * provides:
 * displayWeather()
 * setDrive()
 * setFanSpeed()
 * asctime()
 * updateNote()
 * setupMatrixListeners()
 * loadWeatherAndStartRefresh()
 */

console.log("unit_speed.js loaded");

// Constants
const DEBUG = false;
const REFRESH_INTERVAL = 10; // seconds between refreshes
const RUNNING_MINUTES = 10; // minutes to run before stopping
const SHOW_REFRESH_COUNTDOWN = false;
const DASHBOARD_AIR_QUALITY_DEVICE_EXPIRATION_SECONDS = 30 * 24 * 60 * 60;
let lastRefreshTime = 0;
const AE200_MODE_LABELS = {
  COOL: "Cool",
  HEAT: "Heat",
  AUTO: "Auto",
  DRY: "Dry",
  FAN: "Fan",
  LC_AUTO: "Auto",
};
const FCU_MODE_OPTIONS = ["FAN", "COOL", "DRY", "HEAT", "AUTO"];
const FCU_MODE_DEVICE_ID_KEY = "device_id";
const FCU_MODE_MODE_KEY = "mode";
const AE200_AUTO_MODE_VALUES = ["AUTO", "LC_AUTO"];
const SET_TEMP_TRACK_MIN_F = 55;
const SET_TEMP_TRACK_MAX_F = 85;
const SET_TEMP_TRACK_MIN_C = ((SET_TEMP_TRACK_MIN_F - 32) * 5) / 9;
const SET_TEMP_TRACK_MAX_C = ((SET_TEMP_TRACK_MAX_F - 32) * 5) / 9;
const SET_RANGE_TRACK_MIN_C = SET_TEMP_TRACK_MIN_C;
const SET_RANGE_TRACK_MAX_C = SET_TEMP_TRACK_MAX_C;
const SET_RANGE_STEP_C = 0.5;
const DEFAULT_MIN_SET_RANGE_C = 3.0;
const SET_TEMP_PENDING_TIMEOUT_MS = 30 * 1000;
const SET_TEMP_MATCH_TOLERANCE_C = 0.11;
const UPDATE_STATE_PENDING = "pending";
const UPDATE_STATE_FAILED = "failed";
const UPDATE_DECISION_APPLY = "apply";
const UPDATE_DECISION_HOLD = "hold";
const UPDATE_DECISION_FAILED = "failed";
const SET_RANGE_DEVICE_ID_KEY = "device_id";
const SET_RANGE_LOW_KEY = "set_range_low_c";
const SET_RANGE_HIGH_KEY = "set_range_high_c";
const AUTO_SET_TEMP_DEVICE_ID_KEY = "device_id";
const AUTO_SET_TEMP_HEAT_KEY = "heat_set_temp_c";
const AUTO_SET_TEMP_COOL_KEY = "cool_set_temp_c";
const FCU_TEMP_SOURCE_FCU_DEVICE_ID_KEY = "fcu_device_id";
const FCU_TEMP_SOURCE_SOURCE_DEVICE_ID_KEY = "source_device_id";
const FCU_TEMP_SOURCE_MULTIPLIER_KEY = "multiplier";
const FCU_TEMP_SOURCE_TITLE = "FCU Temperature Sources";
const DEVICE_DISPLAY_NAME_KEY = "display_name";
const DEVICE_TYPE_ICONS = { ERV: "♻️", FCU: "🌀", SENSOR: "📡" };

// Refresh logic
var start = Date.now();
var forceRefresh = false;
const pendingFanRadioIds = new Map();

// Store weather data globally so it can be re-rendered when unit changes
let currentWeatherData = null;

////////////////////////////////////////////////////////////////
// Shared helpers

/**
 * Run at most one instance of an asynchronous operation at a time.
 * Calls made while the operation is active are skipped.
 *
 * @returns {Function} Single-flight async runner.
 */
function createSingleFlight() {
  let inFlight = false;
  return async (operation) => {
    if (inFlight) {
      return false;
    }
    inFlight = true;
    try {
      await operation();
      return true;
    } finally {
      inFlight = false;
    }
  };
}

const runStatusRefresh = createSingleFlight();

/** Clear a pending fan change only if this request still owns it. */
function clearPendingFanChange(pendingChanges, deviceId, change) {
  if (pendingChanges.get(deviceId) === change) {
    pendingChanges.delete(deviceId);
  }
}

/**
 * Decide which fan-speed radio button should be selected for a device.
 *
 * One-dimensional control: "Off" is a state of its own, so an off unit always
 * shows "Off" — regardless of the fan speed it happens to be holding. The
 * AE-200 retains a unit's last fan speed (often Auto = -1) when it is turned
 * off, but for an off unit that held speed is historical only and must never be
 * shown as the active selection. This is why `isOff` is checked before the
 * Auto (-1) case — matching room_dashboard.js.
 *
 * @param {Object} dev - Device data object from /api/v1/status.
 * @param {string|null} pendingRadioId - User selection awaiting confirmation.
 * @returns {string|null} The id of the radio to select, or null if undetermined.
 */
function fanRadioIdForDevice(dev, pendingRadioId = null) {
  if (pendingRadioId) {
    return pendingRadioId;
  }
  const isOff = dev.drive === "Off" || dev.drive === 0 || !dev.drive;
  const currentSpeed = dev.fan_speed || dev.speed;
  const speedValue = currentSpeed != null ? parseInt(currentSpeed) : null;

  if (isOff) {
    return `radio-${dev.device_id}-0`;
  }
  if (speedValue === -1) {
    return `radio-${dev.device_id}-auto`;
  }
  if (speedValue != null) {
    return `radio-${dev.device_id}-${speedValue}`;
  }
  return null;
}

/**
 * Return a display label for the AE-200 operation mode in /api/v1/status.
 *
 * @param {Object} dev - Device data object from /api/v1/status.
 * @returns {string} Human-readable mode label, or "--" when absent.
 */
function modeLabelForDevice(dev) {
  const rawModeString = modeValueForDevice(dev);
  if (rawModeString === "") {
    return "--";
  }
  return AE200_MODE_LABELS[rawModeString] || rawModeString;
}

function modeValueForDevice(dev) {
  const status = dev.status || {};
  const rawMode = dev.mode || status.Mode;
  if (rawMode == null || rawMode === "") {
    return "";
  }
  return String(rawMode).toUpperCase();
}

function isAutoOperationMode(rawMode) {
  return AE200_AUTO_MODE_VALUES.includes(String(rawMode || "").toUpperCase());
}

function isFanOperationMode(rawMode) {
  return String(rawMode || "").toUpperCase() === "FAN";
}

function setTempDisabledTooltip(rawMode) {
  const mode = String(rawMode || "").toUpperCase();
  return mode === "DRY" || mode === "FAN"
    ? `control disabled in ${AE200_MODE_LABELS[mode]} mode.`
    : "";
}

function deviceUpdateTimestampSeconds(dev) {
  if (!dev || dev.logtime == null) {
    return null;
  }
  const logtime = Number(dev.logtime);
  if (!Number.isFinite(logtime)) {
    return null;
  }
  const duration = dev.duration == null ? 1 : Number(dev.duration);
  return Math.floor(logtime + (Number.isFinite(duration) ? duration : 1));
}

function dashboardAirQualityDeviceIsActive(dev, nowDate = new Date()) {
  if (dev?.has_speed_control || dev?.temp10x == null) {
    return false;
  }
  const updatedAt = deviceUpdateTimestampSeconds(dev);
  if (updatedAt == null) {
    return false;
  }
  return (
    nowDate.getTime() / 1000 - updatedAt <=
    DASHBOARD_AIR_QUALITY_DEVICE_EXPIRATION_SECONDS
  );
}

function updateDashboardAirQualityRowVisibility(dev, nowDate = new Date()) {
  if (dev?.has_speed_control || dev?.temp10x == null) {
    return;
  }
  const row = document.querySelector(
    `.device-row[x-data-device-id="${dev.device_id}"]`,
  );
  if (row) {
    row.classList.toggle("hidden", !dashboardAirQualityDeviceIsActive(dev, nowDate));
  }
}

function indexTableIncludesDevice(tableName, dev, nowDate = new Date()) {
  if (tableName === "erv") {
    return dev.device_type === "ERV";
  }
  if (tableName === "fcu") {
    return dev.device_type === "FCU";
  }
  if (tableName === "air-quality") {
    return dashboardAirQualityDeviceIsActive(dev, nowDate);
  }
  return false;
}

function displayNameForDevice(dev) {
  return dev?.display_name || dev?.device_label || dev?.device_name || "";
}

function oldestUpdateForTable(devices, tableName, nowDate = new Date()) {
  if (!Array.isArray(devices)) {
    return null;
  }
  let oldest = null;
  for (const dev of devices) {
    if (!indexTableIncludesDevice(tableName, dev, nowDate)) {
      continue;
    }
    const updateTime = deviceUpdateTimestampSeconds(dev);
    if (
      updateTime != null &&
      (oldest == null || updateTime < oldest.timestampSeconds)
    ) {
      oldest = {
        timestampSeconds: updateTime,
        deviceName: displayNameForDevice(dev),
      };
    }
  }
  return oldest;
}

function oldestUpdateTimestampForTable(devices, tableName, nowDate = new Date()) {
  return oldestUpdateForTable(devices, tableName, nowDate)?.timestampSeconds ?? null;
}

function compactAgeFromSeconds(ageSeconds) {
  const seconds = Math.max(0, Math.floor(ageSeconds));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days}d`;
  }
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months}mo`;
  }
  return `${Math.floor(months / 12)}y`;
}

function padDatePart(value) {
  return String(value).padStart(2, "0");
}

function localDateTimeFromTimestamp(timestampSeconds) {
  const date = new Date(timestampSeconds * 1000);
  return [
    date.getFullYear(),
    "-",
    padDatePart(date.getMonth() + 1),
    "-",
    padDatePart(date.getDate()),
    " ",
    padDatePart(date.getHours()),
    ":",
    padDatePart(date.getMinutes()),
    ":",
    padDatePart(date.getSeconds()),
  ].join("");
}

function tableUpdateSummaryText(
  timestampSeconds,
  nowDate = new Date(),
  sourceDeviceName = "",
) {
  if (timestampSeconds == null) {
    return "";
  }
  const ageSeconds = nowDate.getTime() / 1000 - timestampSeconds;
  const sourceSuffix = sourceDeviceName ? ` from ${sourceDeviceName}` : "";
  return (
    `(oldest update at ${localDateTimeFromTimestamp(timestampSeconds)} - ` +
    `${compactAgeFromSeconds(ageSeconds)} ago${sourceSuffix})`
  );
}

function deviceUpdateText(dev, nowDate = new Date()) {
  const timestampSeconds = deviceUpdateTimestampSeconds(dev);
  if (timestampSeconds == null) {
    return "";
  }
  const ageText =
    dev?.age || compactAgeFromSeconds(nowDate.getTime() / 1000 - timestampSeconds);
  return `${localDateTimeFromTimestamp(timestampSeconds)} - ${ageText} ago`;
}

function deviceUpdateTooltipText(dev, fallbackDeviceName = "", nowDate = new Date()) {
  const deviceName = dev?.device_name || fallbackDeviceName || "";
  const updateText = deviceUpdateText(dev, nowDate);
  if (!updateText) {
    return deviceName;
  }
  return `${deviceName}\nLast updated at ${updateText}`;
}

function updateDeviceNameTooltip(dev, nowDate = new Date()) {
  const labels = document.querySelectorAll(
    `.device-name-context[data-device-id="${dev.device_id}"]`,
  );
  labels.forEach((element) => {
    element.dataset.deviceUpdate = deviceUpdateText(dev, nowDate);
    element.setAttribute(
      "title",
      deviceUpdateTooltipText(dev, element.dataset.deviceName || "", nowDate),
    );
  });
}

function updateTableUpdateSummaries(devices, nowDate = new Date()) {
  for (const tableName of ["erv", "fcu", "air-quality"]) {
    const element = document.getElementById(`oldest-update-${tableName}`);
    if (!element) {
      continue;
    }
    const summary = oldestUpdateForTable(devices, tableName, nowDate);
    element.textContent = tableUpdateSummaryText(
      summary?.timestampSeconds,
      nowDate,
      summary?.deviceName,
    );
  }
}

function ensureModeSelectOption(select, rawMode) {
  if (!select) {
    return;
  }
  const options = select.options || [];
  for (let index = 0; index < options.length; index += 1) {
    if (options[index].value === rawMode) {
      return;
    }
  }
  const option = document.createElement("option");
  option.value = rawMode;
  option.textContent = rawMode === "" ? "--" : AE200_MODE_LABELS[rawMode] || rawMode;
  option.disabled = true;
  option.dataset.extraMode = "true";
  select.insertBefore(option, select.firstChild);
}

function updateModeControlForDevice(dev) {
  const select = document.getElementById(`mode-${dev.device_id}`);
  if (!select || select.dataset.saving === "true") {
    return;
  }
  const rawMode = modeValueForDevice(dev);
  ensureModeSelectOption(select, rawMode);
  select.value = rawMode;
  select.dataset.currentMode = rawMode;
  select.setAttribute("title", rawMode ? `AE-200 Mode: ${rawMode}` : "AE-200 Mode");
}

function autoSetTempRangeForDevice(dev) {
  const status = dev.status || {};
  const heatSetTempC = finiteNumber(dev.heat_set_temp_c, finiteNumber(status.SetTemp2));
  const coolSetTempC = finiteNumber(dev.cool_set_temp_c, finiteNumber(status.SetTemp1));
  if (heatSetTempC === null || coolSetTempC === null) {
    return null;
  }
  return normalizeSetRange(heatSetTempC, coolSetTempC, {
    minRangeC: 0.5,
    trackMinC: SET_RANGE_TRACK_MIN_C,
    trackMaxC: SET_RANGE_TRACK_MAX_C,
  });
}

function setAutoSetTempUnavailable(widget) {
  widget.removeAttribute("data-heat-set-temp-c");
  widget.removeAttribute("data-cool-set-temp-c");
  widget.removeAttribute("data-auto-min-c");
  widget.removeAttribute("data-auto-max-c");
  widget.removeAttribute("title");
  const fill = widget.querySelector("[data-role='auto-range']");
  const heatHandle = widget.querySelector("[data-role='heat']");
  const coolHandle = widget.querySelector("[data-role='cool']");
  if (fill) {
    fill.style.left = "";
    fill.style.width = "";
  }
  if (heatHandle) {
    heatHandle.style.left = "";
  }
  if (coolHandle) {
    coolHandle.style.left = "";
  }
  widget.querySelectorAll(".autosettemp-end-label").forEach((label) => {
    label.removeAttribute("data-temp-c");
    label.textContent = "--";
  });
}

function getAutoSetTempWidgetOptions(widget) {
  const trackMinC = SET_RANGE_TRACK_MIN_C;
  const trackMaxC = SET_RANGE_TRACK_MAX_C;
  return setRangeOptions({
    minRangeC: SET_RANGE_STEP_C,
    trackMinC,
    trackMaxC,
  });
}

function getAutoSetTempRangeFromWidget(widget) {
  const heatC = finiteNumber(widget.dataset.heatSetTempC);
  const coolC = finiteNumber(widget.dataset.coolSetTempC);
  if (heatC === null || coolC === null) {
    return null;
  }
  return normalizeSetRange(heatC, coolC, getAutoSetTempWidgetOptions(widget));
}

function setAutoSetTempSelectedPart(widget, part) {
  widget.dataset.selectedPart = part;
  widget
    .querySelectorAll("[data-role='heat'], [data-role='cool']")
    .forEach((element) => {
      element.classList.toggle("selected", element.dataset.role === part);
    });
}

function renderAutoSetTempRange(widget, heatC, coolC, options = null) {
  if (options) {
    widget.dataset.autoMinC = String(options.trackMinC);
    widget.dataset.autoMaxC = String(options.trackMaxC);
  }

  const initialRange = normalizeSetRange(
    heatC,
    coolC,
    getAutoSetTempWidgetOptions(widget),
  );
  if (!initialRange) {
    setAutoSetTempUnavailable(widget);
    return;
  }
  const resolvedOptions = getAutoSetTempWidgetOptions(widget, initialRange);
  const range = normalizeSetRange(
    initialRange.lowC,
    initialRange.highC,
    resolvedOptions,
  );
  const heatPercent = rangeTempToPercent(range.lowC, resolvedOptions);
  const coolPercent = rangeTempToPercent(range.highC, resolvedOptions);
  const fill = widget.querySelector("[data-role='auto-range']");
  const heatHandle = widget.querySelector("[data-role='heat']");
  const coolHandle = widget.querySelector("[data-role='cool']");
  const heatLabel = widget.querySelector("[data-role='heat-label']");
  const coolLabel = widget.querySelector("[data-role='cool-label']");

  widget.dataset.heatSetTempC = String(range.lowC);
  widget.dataset.coolSetTempC = String(range.highC);
  fill.style.left = `${heatPercent}%`;
  fill.style.width = `${coolPercent - heatPercent}%`;
  heatHandle.style.left = `${heatPercent}%`;
  coolHandle.style.left = `${coolPercent}%`;

  for (const [label, value] of [
    [heatLabel, range.lowC],
    [coolLabel, range.highC],
  ]) {
    label.setAttribute("data-temp-c", String(value));
    label.textContent = TemperatureUtils.formatTemperature(value, false);
  }

  for (const [handle, value, label] of [
    [heatHandle, range.lowC, "Heat"],
    [coolHandle, range.highC, "Cool"],
  ]) {
    handle.setAttribute("title", `${label} ${TemperatureUtils.formatTemperature(value)}`);
    handle.setAttribute("aria-valuemin", String(resolvedOptions.trackMinC));
    handle.setAttribute("aria-valuemax", String(resolvedOptions.trackMaxC));
    handle.setAttribute("aria-valuenow", String(value));
  }
  widget.setAttribute(
    "title",
    `Auto Heat ${TemperatureUtils.formatTemperature(range.lowC)} / Cool ${TemperatureUtils.formatTemperature(range.highC)}`,
  );
}

function renderAutoSetTempWidget(widget, dev) {
  const range = autoSetTempRangeForDevice(dev);
  if (!range) {
    setAutoSetTempUnavailable(widget);
    return;
  }
  const options = setRangeOptions({
    minRangeC: 0.5,
    trackMinC: SET_RANGE_TRACK_MIN_C,
    trackMaxC: SET_RANGE_TRACK_MAX_C,
  });
  const decision = pendingRangeUpdateDecision(widget, range.lowC, range.highC);
  if (decision === UPDATE_DECISION_HOLD) {
    return;
  }
  renderAutoSetTempRange(widget, range.lowC, range.highC, options);
  if (decision === UPDATE_DECISION_FAILED) {
    markRangeFailed(widget);
  }
}

function updateSetTempForDevice(dev) {
  const setTempCell = document.getElementById(`settemp-${dev.device_id}`);
  const setTempDisplay = document.getElementById(`settemp-display-${dev.device_id}`);
  const setTempControls = document.getElementById(`settemp-controls-${dev.device_id}`);
  const autoWidget = document.getElementById(`autosettemp-widget-${dev.device_id}`);
  if (!setTempCell || !setTempDisplay || !setTempControls || !autoWidget) {
    return;
  }

  const status = dev.status || {};
  const operationMode = modeValueForDevice(dev);
  if (isAutoOperationMode(operationMode)) {
    setSingleSetTempControlsDisabled(setTempControls, setTempDisplay, false);
    setTempCell.removeAttribute("title");
    setTempControls.classList.add("hidden");
    autoWidget.classList.remove("hidden");
    if (
      autoWidget.dataset.dragging !== "true" &&
      autoWidget.dataset.saving !== "true"
    ) {
      renderAutoSetTempWidget(autoWidget, dev);
    }
    setTempCell.removeAttribute("data-temp-c");
    setTempDisplay.removeAttribute("data-temp-c");
    clearSingleSetTempPending(setTempDisplay);
    return;
  }

  autoWidget.classList.add("hidden");
  setTempControls.classList.remove("hidden");
  const disabledTooltip = setTempDisabledTooltip(operationMode);
  setSingleSetTempControlsDisabled(
    setTempControls,
    setTempDisplay,
    Boolean(disabledTooltip),
  );
  if (disabledTooltip) {
    setTempCell.setAttribute("title", disabledTooltip);
  } else {
    setTempCell.removeAttribute("title");
  }
  const rawSetTemp = dev.set_temp_c ?? status.SetTemp;

  if (rawSetTemp !== undefined && rawSetTemp !== "") {
    const setTempValue = parseFloat(rawSetTemp);
    if (!Number.isNaN(setTempValue)) {
      const setTempC = setTempValue;
      const decision = pendingSingleSetTempUpdateDecision(setTempDisplay, setTempC);
      if (decision === UPDATE_DECISION_HOLD) {
        return;
      }
      setTempCell.setAttribute("data-temp-c", setTempC.toString());
      setTempDisplay.setAttribute("data-temp-c", setTempC.toString());
      updateStalenessAndTooltip(setTempDisplay, dev);
      setTempDisplay.textContent = TemperatureUtils.formatTemperature(setTempC, false);
      if (decision === UPDATE_DECISION_FAILED) {
        markSingleSetTempFailed(setTempDisplay);
      }
      return;
    }
  }
  if (
    setTempDisplay.dataset.pendingSetTempC &&
    pendingSingleSetTempUpdateDecision(setTempDisplay, null) === UPDATE_DECISION_HOLD
  ) {
    return;
  }
  setTempCell.removeAttribute("data-temp-c");
  setTempDisplay.removeAttribute("data-temp-c");
  setTempDisplay.textContent = "--";
}

function setSingleSetTempControlsDisabled(setTempControls, setTempDisplay, disabled) {
  setTempControls.classList.toggle("settemp-disabled", disabled);
  setTempControls.querySelectorAll(".settemp-btn").forEach((button) => {
    button.disabled = disabled;
  });
  if (disabled) {
    setTempDisplay.setAttribute("aria-disabled", "true");
  } else {
    setTempDisplay.removeAttribute("aria-disabled");
  }
}

/**
 * Update a temperature- or humidity-like cell with staleness and tooltip.
 *
 * @param {HTMLElement|null} cell - The table cell element to update.
 * @param {Object} dev - Device data object from /api/v1/status.
 */
function updateStalenessAndTooltip(cell, dev) {
  if (!cell || !dev) {
    return;
  }

  // Calculate if value is stale (>= 5 minutes = 300 seconds)
  const nowTs = Math.floor(Date.now() / 1000);
  const lastUpdate = (dev.logtime || 0) + (dev.duration || 0);
  const ageSeconds = nowTs - lastUpdate;
  const isStale = ageSeconds >= 300; // 5 minutes

  // Set title attribute for hover tooltip
  if (dev.age) {
    const graphHint = cell.dataset?.chartUrl ? "; click to show graph." : "";
    cell.setAttribute("title", `Last updated: ${dev.age} ago${graphHint}`);
  }

  // Apply color class based on staleness
  cell.classList.remove("temp-stale");
  if (isStale) {
    cell.classList.add("temp-stale");
  }
}

function refreshAirQualityClass(cell) {
  if (
    cell &&
    typeof window !== "undefined" &&
    window.AirQualityThresholds
  ) {
    window.AirQualityThresholds.applyAirQualityClass(cell);
  }
}

/**
 * Render a temperature cell from a tenths-Celsius value.
 *
 * @param {HTMLElement|null} cell - Table cell to update.
 * @param {number|null|undefined} temp10x - Temperature in tenths Celsius.
 * @param {Object|null} dev - Device data object from /api/v1/status.
 */
function updateTemperatureCell(cell, temp10x, dev = null) {
  if (!cell) {
    return;
  }
  if (temp10x === null || temp10x === undefined) {
    cell.removeAttribute("data-temp-c");
    cell.classList.remove("temp-stale");
    cell.textContent = "--";
    return;
  }
  const tempC = parseFloat(temp10x) / 10;
  if (!Number.isFinite(tempC)) {
    cell.removeAttribute("data-temp-c");
    cell.classList.remove("temp-stale");
    cell.textContent = "--";
    return;
  }

  cell.setAttribute("data-temp-c", tempC.toString());
  if (dev) {
    updateStalenessAndTooltip(cell, dev);
  } else {
    cell.classList.remove("temp-stale");
  }

  const includeUnit = !cell.classList.contains("temp-display-no-unit");
  cell.innerHTML = TemperatureUtils.formatTemperature(tempC, includeUnit);
}

function finiteNumber(value, fallback = null) {
  const number = parseFloat(value);
  return Number.isFinite(number) ? number : fallback;
}

function roundTempC(value) {
  return Math.round(value * 10) / 10;
}

function tempValuesMatchC(actualC, expectedC) {
  const actual = finiteNumber(actualC);
  const expected = finiteNumber(expectedC);
  return (
    actual !== null &&
    expected !== null &&
    Math.abs(actual - expected) <= SET_TEMP_MATCH_TOLERANCE_C
  );
}

function setUpdateState(element, state) {
  if (!element || !element.dataset) {
    return;
  }
  if (state) {
    element.dataset.updateState = state;
  } else {
    delete element.dataset.updateState;
  }
}

function markSingleSetTempPending(display, requestedC, nowMs = Date.now()) {
  if (!display || !display.dataset) {
    return;
  }
  display.dataset.pendingSetTempC = String(requestedC);
  display.dataset.pendingUntilMs = String(nowMs + SET_TEMP_PENDING_TIMEOUT_MS);
  setUpdateState(display, UPDATE_STATE_PENDING);
}

function updateSingleSetTempPendingTarget(display, requestedC) {
  if (!display || !display.dataset) {
    return;
  }
  if (!display.dataset.pendingUntilMs) {
    markSingleSetTempPending(display, requestedC);
    return;
  }
  display.dataset.pendingSetTempC = String(requestedC);
  setUpdateState(display, UPDATE_STATE_PENDING);
}

function markSingleSetTempFailed(display) {
  setUpdateState(display, UPDATE_STATE_FAILED);
}

function clearSingleSetTempPending(display) {
  if (!display || !display.dataset) {
    return;
  }
  delete display.dataset.pendingSetTempC;
  delete display.dataset.pendingUntilMs;
  setUpdateState(display, null);
}

function pendingSingleSetTempUpdateDecision(
  display,
  incomingC,
  nowMs = Date.now(),
) {
  const requestedC = finiteNumber(display?.dataset?.pendingSetTempC);
  if (requestedC === null) {
    setUpdateState(display, null);
    return UPDATE_DECISION_APPLY;
  }
  if (tempValuesMatchC(incomingC, requestedC)) {
    clearSingleSetTempPending(display);
    return UPDATE_DECISION_APPLY;
  }
  const pendingUntilMs = finiteNumber(display.dataset.pendingUntilMs, 0);
  if (nowMs <= pendingUntilMs) {
    setUpdateState(display, UPDATE_STATE_PENDING);
    return UPDATE_DECISION_HOLD;
  }
  markSingleSetTempFailed(display);
  return UPDATE_DECISION_FAILED;
}

function markRangePending(widget, lowC, highC, nowMs = Date.now()) {
  if (!widget || !widget.dataset) {
    return;
  }
  widget.dataset.pendingRangeLowC = String(lowC);
  widget.dataset.pendingRangeHighC = String(highC);
  widget.dataset.pendingUntilMs = String(nowMs + SET_TEMP_PENDING_TIMEOUT_MS);
  setUpdateState(widget, UPDATE_STATE_PENDING);
}

function updateRangePendingTarget(widget, lowC, highC) {
  if (!widget || !widget.dataset) {
    return;
  }
  if (!widget.dataset.pendingUntilMs) {
    markRangePending(widget, lowC, highC);
    return;
  }
  widget.dataset.pendingRangeLowC = String(lowC);
  widget.dataset.pendingRangeHighC = String(highC);
  setUpdateState(widget, UPDATE_STATE_PENDING);
}

function markRangeFailed(widget) {
  setUpdateState(widget, UPDATE_STATE_FAILED);
}

function clearRangePending(widget) {
  if (!widget || !widget.dataset) {
    return;
  }
  delete widget.dataset.pendingRangeLowC;
  delete widget.dataset.pendingRangeHighC;
  delete widget.dataset.pendingUntilMs;
  setUpdateState(widget, null);
}

function pendingRangeUpdateDecision(
  widget,
  incomingLowC,
  incomingHighC,
  nowMs = Date.now(),
) {
  const requestedLowC = finiteNumber(widget?.dataset?.pendingRangeLowC);
  const requestedHighC = finiteNumber(widget?.dataset?.pendingRangeHighC);
  if (requestedLowC === null || requestedHighC === null) {
    setUpdateState(widget, null);
    return UPDATE_DECISION_APPLY;
  }
  if (
    tempValuesMatchC(incomingLowC, requestedLowC) &&
    tempValuesMatchC(incomingHighC, requestedHighC)
  ) {
    clearRangePending(widget);
    return UPDATE_DECISION_APPLY;
  }
  const pendingUntilMs = finiteNumber(widget.dataset.pendingUntilMs, 0);
  if (nowMs <= pendingUntilMs) {
    setUpdateState(widget, UPDATE_STATE_PENDING);
    return UPDATE_DECISION_HOLD;
  }
  markRangeFailed(widget);
  return UPDATE_DECISION_FAILED;
}

function setRangeOptions(options = {}) {
  const minRangeC = finiteNumber(
    options.minRangeC,
    DEFAULT_MIN_SET_RANGE_C,
  );
  let trackMinC = finiteNumber(options.trackMinC, SET_RANGE_TRACK_MIN_C);
  let trackMaxC = finiteNumber(options.trackMaxC, SET_RANGE_TRACK_MAX_C);
  if (trackMaxC - trackMinC < minRangeC) {
    trackMaxC = trackMinC + minRangeC;
  }
  return { minRangeC, trackMinC, trackMaxC };
}

function normalizeSetRange(lowC, highC, options = {}) {
  let low = finiteNumber(lowC);
  let high = finiteNumber(highC);
  if (low === null || high === null) {
    return null;
  }

  const opts = setRangeOptions(options);
  if (high < low) {
    [low, high] = [high, low];
  }

  const domainWidth = opts.trackMaxC - opts.trackMinC;
  const wantedWidth = Math.min(
    Math.max(high - low, opts.minRangeC),
    domainWidth,
  );
  high = low + wantedWidth;
  if (high > opts.trackMaxC) {
    high = opts.trackMaxC;
    low = high - wantedWidth;
  }
  if (low < opts.trackMinC) {
    low = opts.trackMinC;
    high = low + wantedWidth;
  }

  return { lowC: roundTempC(low), highC: roundTempC(high) };
}

function resizeSetRangeEndpoint(lowC, highC, endpoint, valueC, options = {}) {
  const opts = setRangeOptions(options);
  const current = normalizeSetRange(lowC, highC, opts);
  if (!current) {
    return null;
  }

  const value = roundTempC(finiteNumber(valueC, current[`${endpoint}C`]));
  let low = current.lowC;
  let high = current.highC;
  if (endpoint === "low") {
    low = Math.min(value, high - opts.minRangeC);
    low = Math.max(opts.trackMinC, low);
  } else {
    high = Math.max(value, low + opts.minRangeC);
    high = Math.min(opts.trackMaxC, high);
  }
  return normalizeSetRange(low, high, opts);
}

function setRangesEqual(first, second) {
  return (
    Boolean(first) &&
    Boolean(second) &&
    first.lowC === second.lowC &&
    first.highC === second.highC
  );
}

function formatAgeSeconds(seconds) {
  if (seconds === null || seconds === undefined) {
    return "--";
  }
  if (seconds < 60) {
    return `${Math.max(0, seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function fcuTempSourcesTitle(unitLabel) {
  const trimmedUnitLabel = String(unitLabel || "").trim();
  return trimmedUnitLabel
    ? `${trimmedUnitLabel}: ${FCU_TEMP_SOURCE_TITLE}`
    : FCU_TEMP_SOURCE_TITLE;
}

function deviceLabelWithIcon(label, deviceType) {
  const icon = DEVICE_TYPE_ICONS[normalizedDeviceType(deviceType)];
  return icon && !label.trimEnd().endsWith(icon) ? `${label} ${icon}` : label;
}

function setFcuTempSourcesTitle(popup, unitLabel) {
  const title = popup.querySelector("[data-role='title']");
  if (title) {
    title.textContent = fcuTempSourcesTitle(unitLabel);
  }
}

function sortedFcuTempSources(sources, roomId = undefined) {
  const sourceList = Array.isArray(sources) ? sources : [];
  const normalizedRoomId =
    typeof roomId === "number" && Number.isInteger(roomId)
      ? roomId
      : typeof roomId === "string" && roomId.trim() !== "" && Number.isInteger(Number(roomId))
        ? Number(roomId)
        : null;
  const activeSources =
    normalizedRoomId === null
      ? sourceList
      : sourceList.filter(
          (source) => source.room_id !== null && source.room_id !== undefined &&
            Number(source.room_id) === normalizedRoomId,
        );
  return activeSources
    .filter((source) => !source.is_stale)
    .concat(activeSources.filter((source) => source.is_stale));
}

function fcuTempSourceLabel(source) {
  const suffix = [];
  if (source.is_fcu_self) {
    suffix.push("FCU");
  }
  if (source.room_name) {
    suffix.push(source.room_name);
  }
  return suffix.length > 0
    ? `${source.device_name} (${suffix.join(", ")})`
    : source.device_name;
}

function parseFcuTempSourceMultiplier(value) {
  const trimmedValue = String(value ?? "").trim();
  if (!trimmedValue) {
    return null;
  }
  const multiplier = Number(trimmedValue);
  return Number.isFinite(multiplier) && multiplier >= 0 ? multiplier : null;
}

function setFcuTempSourcesMessage(popup, message, isError = false) {
  const messageElement = popup.querySelector("[data-role='message']");
  if (!messageElement) {
    return;
  }
  messageElement.textContent = message || "";
  messageElement.classList.toggle("error", isError);
}

function setFcuTempSourcesControlsDisabled(popup, disabled) {
  popup.dataset.saving = disabled ? "true" : "false";
  popup
    .querySelectorAll(
      ".fcu-temp-source-weight, .fcu-temp-sources-actions button",
    )
    .forEach((control) => {
      control.disabled = disabled;
    });
}

function closeFcuTempSourcesPopup(options = {}) {
  const popup = document.getElementById("fcu-temp-sources-popup");
  if (popup && (options.force || popup.dataset.saving !== "true")) {
    popup.classList.add("hidden");
  }
}

function collectFcuTempSourceChanges(popup) {
  const changes = [];
  const inputs = popup.querySelectorAll(".fcu-temp-source-weight");
  for (const input of inputs) {
    const multiplier = parseFcuTempSourceMultiplier(input.value);
    if (multiplier === null) {
      return {
        changes: [],
        error: "Weight must be a nonnegative number.",
      };
    }

    const originalMultiplier = parseFcuTempSourceMultiplier(
      input.dataset.initialMultiplier,
    );
    const fcuDeviceId = parseInt(input.dataset.fcuDeviceId, 10);
    const sourceDeviceId = parseInt(input.dataset.sourceDeviceId, 10);
    if (
      originalMultiplier === null ||
      !Number.isInteger(fcuDeviceId) ||
      !Number.isInteger(sourceDeviceId)
    ) {
      return {
        changes: [],
        error: "Unable to read temperature source row data.",
      };
    }

    if (multiplier !== originalMultiplier) {
      changes.push({
        [FCU_TEMP_SOURCE_FCU_DEVICE_ID_KEY]: fcuDeviceId,
        [FCU_TEMP_SOURCE_SOURCE_DEVICE_ID_KEY]: sourceDeviceId,
        [FCU_TEMP_SOURCE_MULTIPLIER_KEY]: multiplier,
      });
    }
  }
  return { changes, error: "" };
}

function revertFcuTempSourceChanges(popup) {
  popup.querySelectorAll(".fcu-temp-source-weight").forEach((input) => {
    input.value = input.dataset.initialMultiplier;
  });
  setFcuTempSourcesMessage(popup, "");
}

function renderFcuTempSources(popup, data) {
  const tbody = popup.querySelector("[data-role='sources-body']");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";

  const sources = sortedFcuTempSources(data.sources, popup.dataset.roomId);
  if (sources.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "No temperature-reporting sources are assigned to this room.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  for (const source of sources) {
    const row = document.createElement("tr");
    row.classList.toggle("temp-stale", Boolean(source.is_stale));

    const labelCell = document.createElement("td");
    labelCell.textContent = fcuTempSourceLabel(source);

    const tempCell = document.createElement("td");
    if (source.temp10x === null || source.temp10x === undefined) {
      tempCell.textContent = "--";
    } else {
      tempCell.setAttribute("data-temp-c", String(source.temp10x / 10));
      tempCell.classList.add("temp-display", "temp-display-no-unit");
      tempCell.textContent = TemperatureUtils.formatTemperature(
        source.temp10x / 10,
        false,
      );
    }

    const ageCell = document.createElement("td");
    ageCell.textContent = source.is_stale
      ? `${formatAgeSeconds(source.age_seconds)} stale`
      : formatAgeSeconds(source.age_seconds);

    const weightCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.value = String(source.multiplier);
    input.className = "fcu-temp-source-weight";
    input.setAttribute("aria-label", `Weight for ${source.device_name}`);
    input.dataset.fcuDeviceId = String(data.fcu_device_id);
    input.dataset.sourceDeviceId = String(source.source_device_id);
    input.dataset.initialMultiplier = String(source.multiplier);
    weightCell.appendChild(input);

    row.appendChild(labelCell);
    row.appendChild(tempCell);
    row.appendChild(ageCell);
    row.appendChild(weightCell);
    tbody.appendChild(row);
  }
}

async function loadFcuTempSourcesForCell(cell) {
  const popup = document.getElementById("fcu-temp-sources-popup");
  if (!popup || !cell) {
    return;
  }
  const sourcesUrl = cell.dataset.fcuTempSourcesUrl;
  const updateUrl = cell.dataset.fcuTempSourceUpdateUrl;
  if (!sourcesUrl || !updateUrl) {
    return;
  }

  const deviceId = parseInt(cell.dataset.deviceId, 10);
  const displayName = cell.dataset.displayName || cell.dataset.deviceName;
  popup.dataset.updateUrl = updateUrl;
  popup.dataset.roomId = cell.dataset.roomId || "";
  popup.dataset.deviceId = Number.isInteger(deviceId) ? String(deviceId) : "";
  popup.dataset.deviceName = cell.dataset.deviceName || "";
  setFcuTempSourcesTitle(popup, displayName);
  const roomName = popup.querySelector("[data-role='room-name']");
  if (roomName) roomName.textContent = cell.dataset.roomName || "Unassigned";
  popup.classList.remove("hidden");
  setFcuTempSourcesControlsDisabled(popup, false);
  setFcuTempSourcesMessage(popup, "Loading...");
  const tbody = popup.querySelector("[data-role='sources-body']");
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="4">Loading...</td></tr>';
  }

  try {
    const response = await fetch(sourcesUrl);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to load temperature sources.");
    }
    renderFcuTempSources(popup, data);
    setFcuTempSourcesMessage(popup, "");
  } catch (error) {
    console.error("Failed to load FCU temperature sources:", error);
    setFcuTempSourcesMessage(popup, error.message, true);
  }
}

function refreshOpenFcuTempSources(loadSources = loadFcuTempSourcesForCell) {
  const popup = document.getElementById("fcu-temp-sources-popup");
  if (!popup || popup.classList.contains("hidden") || !popup.dataset.deviceId) {
    return false;
  }
  const trigger = document.querySelector(
    `.fcu-temp-sources-trigger[data-device-id="${popup.dataset.deviceId}"]`,
  );
  if (!trigger) return false;
  Promise.resolve(loadSources(trigger)).catch((error) => {
    console.error("Failed to refresh FCU temperature sources:", error);
  });
  return true;
}

async function saveFcuTempSourceMultipliers() {
  const popup = document.getElementById("fcu-temp-sources-popup");
  if (!popup) {
    return;
  }

  const updateUrl = popup.dataset.updateUrl;
  const { changes, error } = collectFcuTempSourceChanges(popup);
  if (error) {
    setFcuTempSourcesMessage(popup, error, true);
    return;
  }
  if (!updateUrl) {
    setFcuTempSourcesMessage(popup, "Unable to save without an update URL.", true);
    return;
  }
  if (changes.length === 0) {
    closeFcuTempSourcesPopup();
    return;
  }

  setFcuTempSourcesControlsDisabled(popup, true);
  setFcuTempSourcesMessage(popup, "Saving...");
  try {
    const response = await fetch(updateUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to save weights.");
    }
    forceRefresh = true;
    closeFcuTempSourcesPopup({ force: true });
  } catch (error) {
    console.error("Failed to save FCU temperature source multipliers:", error);
    setFcuTempSourcesMessage(popup, error.message, true);
  } finally {
    setFcuTempSourcesControlsDisabled(popup, false);
  }
}

function normalizedDeviceDisplayName(value) {
  return String(value || "").trim();
}

function normalizedDeviceType(value) {
  return String(value || "").trim();
}

function deviceRulesEnabledValue(value) {
  if (value === true || value === 1) {
    return true;
  }
  return ["1", "true", "yes", "on"].includes(String(value).trim().toLowerCase());
}

function deviceDisplayNameChanged(currentDisplayName, nextDisplayName) {
  const normalizedNext = normalizedDeviceDisplayName(nextDisplayName);
  return (
    normalizedNext !== "" &&
    normalizedNext !== normalizedDeviceDisplayName(currentDisplayName)
  );
}

function deviceDisplayNamePatchBody(displayName) {
  return { [DEVICE_DISPLAY_NAME_KEY]: normalizedDeviceDisplayName(displayName) };
}

function deviceMetadataUrl(deviceId) {
  return `/api/v1/devices/${deviceId}`;
}

function setDeviceRenameButtonState(popup) {
  const input = document.getElementById("device-rename-display-name");
  const renameButton = popup.querySelector("[data-action='rename-device']");
  if (!input || !renameButton) {
    return;
  }
  renameButton.disabled = !deviceDisplayNameChanged(
    popup.dataset.currentDisplayName,
    input.value,
  );
}

function setDeviceRenameControlsDisabled(popup, disabled) {
  popup.querySelectorAll("input, button").forEach((control) => {
    control.disabled = disabled;
  });
  if (!disabled) {
    const deviceNameInput = document.getElementById("device-rename-device-name");
    const deviceTypeInput = document.getElementById("device-rename-device-type");
    const rulesEnabledInput = document.getElementById(
      "device-rename-rules-enabled",
    );
    const lastUpdateInput = document.getElementById("device-rename-last-update");
    if (deviceNameInput) {
      deviceNameInput.readOnly = true;
    }
    if (deviceTypeInput) {
      deviceTypeInput.readOnly = true;
    }
    if (rulesEnabledInput) {
      rulesEnabledInput.disabled = true;
    }
    if (lastUpdateInput) {
      lastUpdateInput.readOnly = true;
    }
    setDeviceRenameButtonState(popup);
  }
}

function closeDeviceRenamePopup() {
  const popup = document.getElementById("device-rename-popup");
  if (!popup) {
    return;
  }
  popup.classList.add("hidden");
  popup.removeAttribute("style");
  delete popup.dataset.deviceId;
  delete popup.dataset.deviceName;
  delete popup.dataset.deviceType;
  delete popup.dataset.rulesEnabled;
  delete popup.dataset.deviceUpdate;
  delete popup.dataset.currentDisplayName;
}

function setDeviceReadonlyMetadata(popup, deviceType, rulesEnabled) {
  const deviceTypeInput = document.getElementById("device-rename-device-type");
  const rulesEnabledInput = document.getElementById("device-rename-rules-enabled");
  const normalizedType = normalizedDeviceType(deviceType);
  const normalizedRulesEnabled = deviceRulesEnabledValue(rulesEnabled);

  popup.dataset.deviceType = normalizedType;
  popup.dataset.rulesEnabled = String(normalizedRulesEnabled);
  if (deviceTypeInput) {
    deviceTypeInput.value = normalizedType;
  }
  if (rulesEnabledInput) {
    rulesEnabledInput.checked = normalizedRulesEnabled;
    rulesEnabledInput.disabled = true;
  }
}

function positionDeviceRenamePopup(popup, clientX, clientY) {
  const margin = 8;
  const popupWidth = popup.offsetWidth || 360;
  const popupHeight = popup.offsetHeight || 120;
  const left = Math.max(
    margin,
    Math.min(clientX, window.innerWidth - popupWidth - margin),
  );
  const top = Math.max(
    margin,
    Math.min(clientY, window.innerHeight - popupHeight - margin),
  );
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}

function openDeviceRenamePopup(target, event) {
  const popup = document.getElementById("device-rename-popup");
  const deviceNameInput = document.getElementById("device-rename-device-name");
  const displayNameInput = document.getElementById("device-rename-display-name");
  const lastUpdateInput = document.getElementById("device-rename-last-update");
  if (!popup || !deviceNameInput || !displayNameInput) {
    return;
  }

  const deviceId = parseInt(target.dataset.deviceId, 10);
  if (!Number.isInteger(deviceId)) {
    return;
  }
  const deviceName =
    target.dataset.deviceName || target.getAttribute("title") || target.textContent;
  const displayName = target.dataset.displayName || target.textContent;
  const deviceType = target.dataset.deviceType || "";
  const deviceUpdate = target.dataset.deviceUpdate || "";
  const rulesEnabled =
    target.dataset.rulesEnabled === undefined ? true : target.dataset.rulesEnabled;

  popup.dataset.deviceId = String(deviceId);
  popup.dataset.deviceName = deviceName;
  popup.dataset.deviceUpdate = deviceUpdate;
  popup.dataset.currentDisplayName = displayName;
  deviceNameInput.value = deviceName;
  displayNameInput.value = displayName;
  if (lastUpdateInput) {
    lastUpdateInput.value = deviceUpdate || "--";
  }
  setDeviceReadonlyMetadata(popup, deviceType, rulesEnabled);

  popup.classList.remove("hidden");
  setDeviceRenameControlsDisabled(popup, false);
  positionDeviceRenamePopup(popup, event.clientX, event.clientY);
  displayNameInput.focus();
  displayNameInput.select();
}

async function patchDeviceDisplayName(deviceId, displayName, updateUrl = undefined) {
  let response;
  try {
    response = await fetch(updateUrl || deviceMetadataUrl(deviceId), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(deviceDisplayNamePatchBody(displayName)),
    });
  } catch (error) {
    throw new Error(`NETWORK ${error.message}`);
  }

  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new Error(`${response.status} ${data.error || response.statusText}`);
  }
  return data;
}

function applyDeviceDisplayName(
  deviceId,
  deviceName,
  displayName,
  deviceType = undefined,
  rulesEnabled = undefined,
) {
  const label = normalizedDeviceDisplayName(displayName) || deviceName;
  document
    .querySelectorAll(`.device-name-context[data-device-id="${deviceId}"]`)
    .forEach((element) => {
      element.textContent = deviceLabelWithIcon(label, deviceType);
      element.dataset.deviceName = deviceName;
      element.dataset.displayName = label;
      if (deviceType !== undefined) {
        element.dataset.deviceType = normalizedDeviceType(deviceType);
      }
      if (rulesEnabled !== undefined) {
        element.dataset.rulesEnabled = String(
          deviceRulesEnabledValue(rulesEnabled),
        );
      }
      const isFcuTempSourcesTrigger =
        element.classList?.contains("fcu-temp-sources-trigger");
      if (isFcuTempSourcesTrigger) {
        element.setAttribute("aria-label", `Edit temperature sources for ${label}`);
      }
      const title = isFcuTempSourcesTrigger
        ? `Edit temperature sources for ${label}`
        : element.dataset.deviceUpdate
          ? `${deviceName}\nLast updated at ${element.dataset.deviceUpdate}`
          : deviceName;
      element.setAttribute("title", title);
    });
}

async function submitDeviceDisplayName(displayName) {
  const popup = document.getElementById("device-rename-popup");
  if (!popup) {
    return;
  }
  const deviceId = parseInt(popup.dataset.deviceId, 10);
  const deviceName = popup.dataset.deviceName || "";
  if (!Number.isInteger(deviceId) || !deviceName) {
    closeDeviceRenamePopup();
    return;
  }

  setDeviceRenameControlsDisabled(popup, true);
  try {
    const data = await patchDeviceDisplayName(deviceId, displayName);
    const savedDisplayName = data.display_name || displayName || deviceName;
    applyDeviceDisplayName(
      deviceId,
      deviceName,
      savedDisplayName,
      data.device_type ?? popup.dataset.deviceType,
      data.rules_enabled ?? popup.dataset.rulesEnabled,
    );
    forceRefresh = true;
    closeDeviceRenamePopup();
  } catch (error) {
    console.error("Failed to update device display name:", error);
    alert(`Error ${error.message}`);
    closeDeviceRenamePopup();
  } finally {
    if (!popup.classList.contains("hidden")) {
      setDeviceRenameControlsDisabled(popup, false);
    }
  }
}

function setupDeviceRenamePopupControls() {
  document.querySelectorAll(".device-name-context").forEach((deviceName) => {
    deviceName.addEventListener("contextmenu", function (event) {
      event.preventDefault();
      event.stopPropagation();
      openDeviceRenamePopup(this, event);
    });
  });

  const popup = document.getElementById("device-rename-popup");
  if (!popup) {
    return;
  }
  const displayNameInput = document.getElementById("device-rename-display-name");
  if (displayNameInput) {
    displayNameInput.addEventListener("input", () => {
      setDeviceRenameButtonState(popup);
    });
    displayNameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (
          deviceDisplayNameChanged(
            popup.dataset.currentDisplayName,
            displayNameInput.value,
          )
        ) {
          submitDeviceDisplayName(displayNameInput.value);
        }
      }
    });
  }

  const renameButton = popup.querySelector("[data-action='rename-device']");
  if (renameButton && displayNameInput) {
    renameButton.addEventListener("click", () => {
      submitDeviceDisplayName(displayNameInput.value);
    });
  }

  const resetButton = popup.querySelector("[data-action='reset-device-name']");
  if (resetButton) {
    resetButton.addEventListener("click", () => {
      const deviceName = popup.dataset.deviceName || "";
      if (displayNameInput) {
        displayNameInput.value = deviceName;
        setDeviceRenameButtonState(popup);
      }
      submitDeviceDisplayName(deviceName);
    });
  }

  const cancelButton = popup.querySelector("[data-action='cancel-device-rename']");
  if (cancelButton) {
    cancelButton.addEventListener("click", closeDeviceRenamePopup);
  }

  document.addEventListener("click", (event) => {
    if (!popup.classList.contains("hidden") && !popup.contains(event.target)) {
      closeDeviceRenamePopup();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDeviceRenamePopup();
    }
  });
}

////////////////////////////////////////////////////////////////
// Weather display functions
function displayWeather(weatherInfo) {
  const weatherDiv = document.getElementById("weather");
  if (!weatherDiv || !weatherInfo) {
    return;
  }

  const rows = [];
  const appendIcon = (container, iconUrl) => {
    if (!iconUrl) {
      return;
    }
    const icon = document.createElement("img");
    icon.src = iconUrl;
    icon.alt = "weather icon";
    icon.className = "weather-icon";
    container.append(" ", icon);
  };
  const appendCurrent = (temperature, stationName, conditions, iconUrl) => {
    const row = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = "Current:";
    row.append(label, " ");
    if (temperature === null || temperature === undefined) {
      row.append("N/A");
    } else {
      row.append(TemperatureUtils.formatTemperature(temperature));
      if (stationName) {
        row.append(` (${stationName})`);
      }
    }
    appendIcon(row, iconUrl);
    if (conditions) {
      row.append(" ", conditions);
    }
    rows.push(row);
  };

  if (Array.isArray(weatherInfo.stations)) {
    weatherInfo.stations.forEach((station) => {
      appendCurrent(
        station.temperature,
        station.station_name,
        station.conditions,
        station.icon,
      );
    });
  } else if (weatherInfo.current) {
    appendCurrent(
      weatherInfo.current.temperature,
      weatherInfo.current.station_name || "Boston Logan Airport",
      weatherInfo.current.conditions,
      weatherInfo.current.icon,
    );
  }

  if (weatherInfo.forecast && weatherInfo.forecast.length > 0) {
    const heading = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = "Forecast for CALA:";
    heading.appendChild(label);
    rows.push(heading);
    weatherInfo.forecast.forEach((period) => {
      const tempF = parseFloat(period.temperature);
      const tempC = TemperatureUtils.fahrenheitToCelsius(tempF);
      const row = document.createElement("div");
      row.append(period.time || "--", " ");
      if (Number.isFinite(tempC)) {
        row.append(TemperatureUtils.formatTemperature(tempC));
      } else {
        row.append("--");
      }
      appendIcon(row, period.icon);
      if (period.conditions) {
        row.append(" ", period.conditions);
      }
      rows.push(row);
    });
  }
  weatherDiv.replaceChildren(...rows);
  currentWeatherData = weatherInfo;
}

////////////////////////////////////////////////////////////////

// Function called to set the fan drive
async function setDrive(device_id, drive) {
  console.log(`setDrive(${device_id},${drive})`);
  try {
    const response = await fetch("/api/v1/set_drive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: device_id, drive: drive }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Unable to set drive.");
    }
    console.log("Set drive: result=", result);
    forceRefresh = true;
    return true;
  } catch (e) {
    console.error("Failed to set drive:", e);
    alert("Error setting drive.");
    return false;
  }
}

// Function called to set the fan_speed
async function setFanSpeed(device_id, fan_speed) {
  console.log(`setFanSpeed(${device_id},${fan_speed})`);
  try {
    console.log("sending", device_id, fan_speed);
    const response = await fetch("/api/v1/set_fan_speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: device_id, fan_speed: fan_speed }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Unable to set fan speed.");
    }
    console.log("Set fan_speed: result=", result);
    forceRefresh = true;
    return true;
  } catch (e) {
    console.error("Failed to set fan_speed:", e);
    alert("Error setting fan_speed.");
    return false;
  }
}

async function setDeviceMode(deviceId, mode) {
  try {
    const response = await fetch("/api/v1/set_mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        [FCU_MODE_DEVICE_ID_KEY]: deviceId,
        [FCU_MODE_MODE_KEY]: mode,
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Unable to set mode.");
    }
    forceRefresh = true;
    return result;
  } catch (e) {
    console.error("Failed to set mode:", e);
    throw e;
  }
}

function asctime(date) {
  const zeroPad = (num, places) => String(num).padStart(places, "0");
  return (
    date.getFullYear() +
    "-" +
    zeroPad(date.getMonth() + 1, 2) +
    "-" +
    zeroPad(date.getDate(), 2) +
    " " +
    zeroPad(date.getHours(), 2) +
    ":" +
    zeroPad(date.getMinutes(), 2) +
    ":" +
    zeroPad(date.getSeconds(), 2)
  );
}

/**
 * Update device notes via API.
 * @param {number} deviceId - Device ID
 * @param {string|null} notes - Notes text (null to clear)
 */
async function updateNote(deviceId, notes) {
  try {
    const response = await fetch("/api/v1/update_note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, notes: notes }),
    });
    await response.json();
    forceRefresh = true;
  } catch (e) {
    console.error("Failed to update note:", e);
    alert("Error updating note.");
  }
}

// Handle all user events
function setupMatrixListeners() {
  // Add event listeners for radio buttons (including Off button)
  const radioButtons = document.querySelectorAll(
    'input[type="radio"][x-data-device-id]',
  );
  radioButtons.forEach((radio) => {
    radio.addEventListener("change", async function () {
      const deviceId = parseInt(this.getAttribute("x-data-device-id"));
      const fan_speed = parseInt(this.getAttribute("x-data-fan_speed"));
      const pendingChange = { radioId: this.id };
      pendingFanRadioIds.set(deviceId, pendingChange);

      try {
        // Off button (0): turn off drive
        if (fan_speed === 0) {
          await setDrive(deviceId, 0);
        }
        // Speed buttons: turn on drive AND set speed
        else {
          await Promise.all([
            setDrive(deviceId, 1),
            setFanSpeed(deviceId, fan_speed),
          ]);
        }
      } finally {
        clearPendingFanChange(pendingFanRadioIds, deviceId, pendingChange);
        forceRefresh = true;
      }
    });
  });

  // Add event listeners for editable notes
  setupEditableNotes();

  // Add event listeners for set temperature controls
  setupSetTempControls();

  // Add event listeners for Auto Heat/Cool set temperature controls
  setupAutoSetTempControls();

  // Add event listeners for FCU set ranges.
  setupSetRangeControls();

  // Add event listeners for FCU operation modes.
  setupModeControls();

  // Add event listeners for "Disable for" ± controls
  setupDisableForControls();

  // Add event listener for the inline rules-disabled [x] button.
  setupRulesDisabledBadgeControls();

  // Add event listeners for calculated room-temperature source weights.
  setupFcuTempSourcePopupControls();

  // Add right-click device display-name editor.
  setupDeviceRenamePopupControls();
}

function setupModeControls() {
  document.querySelectorAll(".mode-select").forEach((select) => {
    select.addEventListener("change", function () {
      const deviceId = parseInt(this.dataset.deviceId, 10);
      const mode = this.value;
      const previousMode = this.dataset.currentMode || "";
      if (
        Number.isNaN(deviceId) ||
        !FCU_MODE_OPTIONS.includes(mode) ||
        mode === previousMode
      ) {
        return;
      }

      this.dataset.saving = "true";
      this.dataset.currentMode = mode;
      this.disabled = true;
      updateSetRangeModeState(
        document.getElementById(`setrange-widget-${deviceId}`),
        mode,
      );
      setDeviceMode(deviceId, mode)
        .then((result) => {
          const savedMode = result.mode || mode;
          ensureModeSelectOption(this, savedMode);
          this.value = savedMode;
          this.dataset.currentMode = savedMode;
          updateSetRangeModeState(
            document.getElementById(`setrange-widget-${deviceId}`),
            savedMode,
          );
        })
        .catch(() => {
          ensureModeSelectOption(this, previousMode);
          this.value = previousMode;
          this.dataset.currentMode = previousMode;
          updateSetRangeModeState(
            document.getElementById(`setrange-widget-${deviceId}`),
            previousMode,
          );
          alert("Error setting mode.");
        })
        .finally(() => {
          delete this.dataset.saving;
          this.disabled = false;
        });
    });
  });
}

function setupFcuTempSourcePopupControls() {
  document.querySelectorAll(".fcu-temp-sources-trigger").forEach((trigger) => {
    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      loadFcuTempSourcesForCell(this);
    });
    trigger.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        loadFcuTempSourcesForCell(this);
      }
    });
  });

  const popup = document.getElementById("fcu-temp-sources-popup");
  if (!popup) {
    return;
  }
  const saveButton = popup.querySelector("[data-action='save-fcu-temp-sources']");
  if (saveButton) {
    saveButton.addEventListener("click", saveFcuTempSourceMultipliers);
  }
  const revertButton = popup.querySelector("[data-action='revert-fcu-temp-sources']");
  if (revertButton) {
    revertButton.addEventListener("click", () => {
      revertFcuTempSourceChanges(popup);
    });
  }
  const cancelButton = popup.querySelector("[data-action='cancel-fcu-temp-sources']");
  if (cancelButton) {
    cancelButton.addEventListener("click", () => {
      closeFcuTempSourcesPopup();
    });
  }
  popup.addEventListener("click", (event) => {
    if (event.target === popup) {
      closeFcuTempSourcesPopup();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeFcuTempSourcesPopup();
    }
  });
}

/**
 * Initialize click-to-edit functionality for note fields.
 */
function setupEditableNotes() {
  document.querySelectorAll(".editable-notes").forEach((noteElement) => {
    noteElement.addEventListener("click", function () {
      if (this.classList.contains("editing")) {
        return;
      }

      const deviceId = parseInt(this.getAttribute("data-device-id"));
      const currentText = this.textContent.trim();
      const input = createNoteInput(currentText);

      this.classList.add("editing");
      this.innerHTML = "";
      this.appendChild(input);
      input.focus();
      input.select();

      setupNoteInputHandlers(input, this, deviceId, currentText);
    });
  });
}

/**
 * Initialize set temperature controls using compact up/down buttons.
 * Buttons operate in the currently selected UI unit but send Celsius to backend.
 */
function setupSetTempControls() {
  document.querySelectorAll(".settemp-btn").forEach((button) => {
    button.addEventListener("click", function () {
      const deviceId = parseInt(this.getAttribute("data-device-id"));
      const delta = parseFloat(this.getAttribute("data-delta") || "0");
      const display = document.getElementById(`settemp-display-${deviceId}`);
      if (!display) {
        return;
      }

      const currentCAttr = display.getAttribute("data-temp-c");
      let currentC = currentCAttr ? parseFloat(currentCAttr) : NaN;

      // If we do not have a current value yet, initialize from a reasonable default (e.g., 21°C)
      if (Number.isNaN(currentC)) {
        currentC = 21.0;
      }

      // Work in UI units for the step, then convert back to Celsius
      const useFahrenheit = TemperatureUtils.getTemperatureUnitPreference();
      let currentUI = currentC;
      if (useFahrenheit) {
        currentUI = TemperatureUtils.celsiusToFahrenheit(currentC);
      }

      let newUI = currentUI + delta;

      const minUI = useFahrenheit ? SET_TEMP_TRACK_MIN_F : SET_TEMP_TRACK_MIN_C;
      const maxUI = useFahrenheit ? SET_TEMP_TRACK_MAX_F : SET_TEMP_TRACK_MAX_C;
      if (newUI < minUI) {
        newUI = minUI;
      } else if (newUI > maxUI) {
        newUI = maxUI;
      }

      let newC = newUI;
      if (useFahrenheit) {
        newC = TemperatureUtils.fahrenheitToCelsius(newUI);
      }

      // Round to a single decimal in Celsius
      newC = Math.round(newC * 10) / 10;

      // Optimistically update UI
      display.setAttribute("data-temp-c", newC.toString());
      display.textContent = TemperatureUtils.formatTemperature(newC, false);
      markSingleSetTempPending(display, newC);

      // Send to backend in Celsius
      setDeviceSetTemp(deviceId, newC, display);
    });
  });
}

/**
 * Call backend API to set device set temperature in Celsius.
 * @param {number} deviceId
 * @param {number} setTempC
 * @param {HTMLElement|null} display
 */
async function setDeviceSetTemp(deviceId, setTempC, display = null) {
  try {
    const response = await fetch("/api/v1/set_temp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, set_temp_c: setTempC }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Unable to save set temperature.");
    }
    if (DEBUG) {
      console.log("Set temp result:", result);
    }
    if (result.set_temp_c !== undefined) {
      updateSingleSetTempPendingTarget(display, result.set_temp_c);
    }
    // Force data refresh to pick up canonical values from AE-200
    forceRefresh = true;
  } catch (e) {
    console.error("Failed to set temperature:", e);
    markSingleSetTempFailed(display);
    alert("Error setting temperature.");
  }
}

function pointerEventToAutoSetTemp(widget, event) {
  const track = widget.querySelector(".autosettemp-track");
  const range = getAutoSetTempRangeFromWidget(widget);
  const options = getAutoSetTempWidgetOptions(widget, range);
  const rect = track.getBoundingClientRect();
  const fraction = Math.min(
    1,
    Math.max(0, (event.clientX - rect.left) / rect.width),
  );
  return roundTempC(
    options.trackMinC + fraction * (options.trackMaxC - options.trackMinC),
  );
}

function autoSetTempEndpointForPart(part) {
  if (part === "heat") {
    return "low";
  }
  if (part === "cool") {
    return "high";
  }
  return null;
}

function applyAutoSetTempPointerValue(widget, event) {
  const drag = widget._autoSetTempDrag;
  const current = getAutoSetTempRangeFromWidget(widget);
  if (!drag || !current) {
    return;
  }

  const endpoint = autoSetTempEndpointForPart(drag.part);
  if (!endpoint) {
    return;
  }
  const options = getAutoSetTempWidgetOptions(widget, current);
  const nextRange = resizeSetRangeEndpoint(
    current.lowC,
    current.highC,
    endpoint,
    pointerEventToAutoSetTemp(widget, event),
    options,
  );
  if (nextRange && !setRangesEqual(current, nextRange)) {
    drag.changed = true;
    renderAutoSetTempRange(widget, nextRange.lowC, nextRange.highC);
  }
}

function autoSetTempPartFromPointerTarget(event) {
  const role = event.currentTarget?.dataset?.role || event.target?.dataset?.role;
  if (role === "heat" || role === "cool") {
    return role;
  }
  return null;
}

function handleAutoSetTempPointerDown(event) {
  const widget = event.currentTarget.closest(".autosettemp-widget");
  const current = getAutoSetTempRangeFromWidget(widget);
  if (!current) {
    return;
  }

  const part = autoSetTempPartFromPointerTarget(event);
  if (!part) {
    return;
  }
  event.preventDefault();
  setAutoSetTempSelectedPart(widget, part);
  if (typeof event.target.focus === "function") {
    event.target.focus();
  }

  widget.dataset.dragging = "true";
  widget._autoSetTempDrag = {
    part,
    changed: false,
  };
  event.currentTarget.setPointerCapture(event.pointerId);
}

function handleAutoSetTempPointerMove(event) {
  const widget = event.currentTarget.closest(".autosettemp-widget");
  if (widget.dataset.dragging !== "true") {
    return;
  }
  applyAutoSetTempPointerValue(widget, event);
}

function finishAutoSetTempPointerDrag(event) {
  const widget = event.currentTarget.closest(".autosettemp-widget");
  if (widget.dataset.dragging !== "true") {
    return;
  }
  delete widget.dataset.dragging;
  const shouldSave = Boolean(widget._autoSetTempDrag?.changed);
  delete widget._autoSetTempDrag;
  event.currentTarget.releasePointerCapture(event.pointerId);
  if (shouldSave) {
    saveAutoSetTempWidget(widget);
  }
}

function handleAutoSetTempKeyDown(event) {
  const widget = event.currentTarget.closest(".autosettemp-widget");
  const current = getAutoSetTempRangeFromWidget(widget);
  if (!current) {
    return;
  }

  const keyDeltas = {
    ArrowLeft: -SET_RANGE_STEP_C,
    ArrowDown: -SET_RANGE_STEP_C,
    ArrowRight: SET_RANGE_STEP_C,
    ArrowUp: SET_RANGE_STEP_C,
  };
  const delta = keyDeltas[event.key];
  if (delta === undefined) {
    return;
  }
  event.preventDefault();

  const part = event.currentTarget.dataset.role || widget.dataset.selectedPart;
  const endpoint = autoSetTempEndpointForPart(part);
  if (!endpoint) {
    return;
  }
  setAutoSetTempSelectedPart(widget, part);
  const options = getAutoSetTempWidgetOptions(widget, current);
  const currentValue = endpoint === "low" ? current.lowC : current.highC;
  const nextRange = resizeSetRangeEndpoint(
    current.lowC,
    current.highC,
    endpoint,
    currentValue + delta,
    options,
  );
  if (nextRange) {
    renderAutoSetTempRange(widget, nextRange.lowC, nextRange.highC);
    saveAutoSetTempWidget(widget);
  }
}

function saveAutoSetTempWidget(widget) {
  const range = getAutoSetTempRangeFromWidget(widget);
  if (!range) {
    return Promise.resolve();
  }
  const deviceId = parseInt(widget.dataset.deviceId, 10);
  const updateUrl = widget.dataset.updateUrl || "/api/v1/set_auto_temp";
  widget.dataset.saving = "true";
  markRangePending(widget, range.lowC, range.highC);
  return fetch(updateUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      [AUTO_SET_TEMP_DEVICE_ID_KEY]: deviceId,
      [AUTO_SET_TEMP_HEAT_KEY]: range.lowC,
      [AUTO_SET_TEMP_COOL_KEY]: range.highC,
    }),
  })
    .then(async (response) => {
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Unable to save Auto setpoints.");
      }
      renderAutoSetTempRange(
        widget,
        result.heat_set_temp_c,
        result.cool_set_temp_c,
      );
      updateRangePendingTarget(
        widget,
        result.heat_set_temp_c,
        result.cool_set_temp_c,
      );
      forceRefresh = true;
    })
    .catch((error) => {
      console.error("Failed to save Auto setpoints:", error);
      markRangeFailed(widget);
      alert("Error setting Auto heat/cool temperatures.");
    })
    .finally(() => {
      delete widget.dataset.saving;
    });
}

function setupAutoSetTempControls() {
  document.querySelectorAll(".autosettemp-widget").forEach((widget) => {
    setAutoSetTempSelectedPart(
      widget,
      widget.dataset.selectedPart === "cool" ? "cool" : "heat",
    );

    widget
      .querySelectorAll("[data-role='heat'], [data-role='cool']")
      .forEach((element) => {
        element.addEventListener("pointerdown", handleAutoSetTempPointerDown);
        element.addEventListener("pointermove", handleAutoSetTempPointerMove);
        element.addEventListener("pointerup", finishAutoSetTempPointerDrag);
        element.addEventListener("pointercancel", finishAutoSetTempPointerDrag);
        element.addEventListener("keydown", handleAutoSetTempKeyDown);
      });
  });
}

function getSetRangeWidgetOptions(widget) {
  const minRangeC = finiteNumber(
    widget.dataset.minRangeC,
    DEFAULT_MIN_SET_RANGE_C,
  );
  const trackMinC = SET_RANGE_TRACK_MIN_C;
  const trackMaxC = SET_RANGE_TRACK_MAX_C;
  return setRangeOptions({ minRangeC, trackMinC, trackMaxC });
}

function getSetRangeFromWidget(widget) {
  const lowC = finiteNumber(widget.dataset.setRangeLowC);
  const highC = finiteNumber(widget.dataset.setRangeHighC);
  if (lowC === null || highC === null) {
    return null;
  }
  return normalizeSetRange(lowC, highC, getSetRangeWidgetOptions(widget));
}

function setSetRangeSelectedPart(widget, part) {
  widget.dataset.selectedPart = part;
  widget
    .querySelectorAll("[data-role='low'], [data-role='high']")
    .forEach((element) => {
      element.classList.toggle("selected", element.dataset.role === part);
    });
}

function setSetRangeUnavailable(widget) {
  widget.removeAttribute("data-set-range-low-c");
  widget.removeAttribute("data-set-range-high-c");
  widget.querySelectorAll(".setrange-end-label").forEach((label) => {
    label.removeAttribute("data-temp-c");
    label.textContent = "--";
  });
}

function updateSetRangeModeState(widget, rawMode) {
  if (!widget) {
    return;
  }
  const mode = String(rawMode || "").toUpperCase();
  widget.dataset.mode = mode;
  widget.setAttribute(
    "title",
    "Rule Set Range is stored for local rules.",
  );
}

function rangeTempToPercent(valueC, options) {
  return ((valueC - options.trackMinC) / (options.trackMaxC - options.trackMinC)) * 100;
}

function pointerEventToRangeTemp(widget, event) {
  const track = widget.querySelector(".setrange-track");
  const range = getSetRangeFromWidget(widget);
  const options = getSetRangeWidgetOptions(widget, range);
  const rect = track.getBoundingClientRect();
  const fraction = Math.min(
    1,
    Math.max(0, (event.clientX - rect.left) / rect.width),
  );
  return roundTempC(
    options.trackMinC + fraction * (options.trackMaxC - options.trackMinC),
  );
}

function renderSetRangeWidget(widget, lowC, highC, minRangeC = null) {
  if (minRangeC !== null && minRangeC !== undefined) {
    widget.dataset.minRangeC = String(minRangeC);
  }

  const initialRange = normalizeSetRange(lowC, highC, {
    minRangeC: finiteNumber(widget.dataset.minRangeC, DEFAULT_MIN_SET_RANGE_C),
    trackMinC: SET_RANGE_TRACK_MIN_C,
    trackMaxC: SET_RANGE_TRACK_MAX_C,
  });
  if (!initialRange) {
    setSetRangeUnavailable(widget);
    return;
  }

  const options = getSetRangeWidgetOptions(widget, initialRange);
  const range = normalizeSetRange(initialRange.lowC, initialRange.highC, options);
  widget.dataset.setRangeLowC = String(range.lowC);
  widget.dataset.setRangeHighC = String(range.highC);

  const lowPercent = rangeTempToPercent(range.lowC, options);
  const highPercent = rangeTempToPercent(range.highC, options);
  const fill = widget.querySelector("[data-role='middle']");
  const lowHandle = widget.querySelector("[data-role='low']");
  const highHandle = widget.querySelector("[data-role='high']");
  const lowLabel = widget.querySelector("[data-role='low-label']");
  const highLabel = widget.querySelector("[data-role='high-label']");

  fill.style.left = `${lowPercent}%`;
  fill.style.width = `${highPercent - lowPercent}%`;
  lowHandle.style.left = `${lowPercent}%`;
  highHandle.style.left = `${highPercent}%`;

  for (const [label, value] of [
    [lowLabel, range.lowC],
    [highLabel, range.highC],
  ]) {
    label.setAttribute("data-temp-c", String(value));
    label.textContent = TemperatureUtils.formatTemperature(value, false);
  }

  for (const [handle, value, label] of [
    [lowHandle, range.lowC, "lower"],
    [highHandle, range.highC, "upper"],
  ]) {
    handle.setAttribute("title", `${label} ${TemperatureUtils.formatTemperature(value)}`);
    handle.setAttribute("aria-valuemin", String(options.trackMinC));
    handle.setAttribute("aria-valuemax", String(options.trackMaxC));
    handle.setAttribute("aria-valuenow", String(value));
  }
  fill.setAttribute(
    "title",
    `${TemperatureUtils.formatTemperature(range.lowC)} - ${TemperatureUtils.formatTemperature(range.highC)}`,
  );
}

function saveSetRangeWidget(widget) {
  const range = getSetRangeFromWidget(widget);
  if (!range) {
    return Promise.resolve();
  }
  const deviceId = parseInt(widget.dataset.deviceId, 10);
  const updateUrl = widget.dataset.updateUrl || "/api/v1/set_range";
  widget.dataset.saving = "true";
  markRangePending(widget, range.lowC, range.highC);
  return fetch(updateUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      [SET_RANGE_DEVICE_ID_KEY]: deviceId,
      [SET_RANGE_LOW_KEY]: range.lowC,
      [SET_RANGE_HIGH_KEY]: range.highC,
    }),
  })
    .then(async (response) => {
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Unable to save set range.");
      }
      renderSetRangeWidget(
        widget,
        result.set_range_low_c,
        result.set_range_high_c,
        result.min_set_range_c,
      );
      updateRangePendingTarget(
        widget,
        result.set_range_low_c,
        result.set_range_high_c,
      );
      forceRefresh = true;
    })
    .catch((error) => {
      console.error("Failed to save set range:", error);
      markRangeFailed(widget);
      alert("Error setting range.");
    })
    .finally(() => {
      delete widget.dataset.saving;
    });
}

function updateSetRangeForDevice(dev) {
  const widget = document.getElementById(`setrange-widget-${dev.device_id}`);
  if (
    !widget ||
    widget.dataset.dragging === "true" ||
    widget.dataset.saving === "true"
  ) {
    return;
  }
  updateSetRangeModeState(widget, modeValueForDevice(dev));
  if (
    dev.set_range_low_c === undefined ||
    dev.set_range_high_c === undefined
  ) {
    setSetRangeUnavailable(widget);
    return;
  }
  const incomingRange = normalizeSetRange(
    dev.set_range_low_c,
    dev.set_range_high_c,
    getSetRangeWidgetOptions(widget),
  );
  if (!incomingRange) {
    setSetRangeUnavailable(widget);
    return;
  }
  const decision = pendingRangeUpdateDecision(
    widget,
    incomingRange.lowC,
    incomingRange.highC,
  );
  if (decision === UPDATE_DECISION_HOLD) {
    return;
  }
  renderSetRangeWidget(
    widget,
    incomingRange.lowC,
    incomingRange.highC,
    dev.min_set_range_c,
  );
  if (decision === UPDATE_DECISION_FAILED) {
    markRangeFailed(widget);
  }
}

function applySetRangePointerValue(widget, event) {
  const drag = widget._setRangeDrag;
  const current = getSetRangeFromWidget(widget);
  if (!drag || !current) {
    return;
  }

  const options = getSetRangeWidgetOptions(widget, current);
  const nextRange = resizeSetRangeEndpoint(
    current.lowC,
    current.highC,
    drag.part,
    pointerEventToRangeTemp(widget, event),
    options,
  );
  if (nextRange && !setRangesEqual(current, nextRange)) {
    drag.changed = true;
    renderSetRangeWidget(widget, nextRange.lowC, nextRange.highC);
  }
}

function setRangePartFromPointerTarget(event) {
  const role = event.currentTarget?.dataset?.role || event.target?.dataset?.role;
  if (role === "low" || role === "high") {
    return role;
  }
  return null;
}

function handleSetRangePointerDown(event) {
  const widget = event.currentTarget.closest(".setrange-widget");
  const current = getSetRangeFromWidget(widget);
  if (!current) {
    return;
  }

  const part = setRangePartFromPointerTarget(event);
  if (!part) {
    return;
  }
  event.preventDefault();
  setSetRangeSelectedPart(widget, part);
  if (typeof event.target.focus === "function") {
    event.target.focus();
  }

  widget.dataset.dragging = "true";
  widget._setRangeDrag = {
    part,
    changed: false,
  };
  event.currentTarget.setPointerCapture(event.pointerId);
}

function handleSetRangePointerMove(event) {
  const widget = event.currentTarget.closest(".setrange-widget");
  if (widget.dataset.dragging !== "true") {
    return;
  }
  applySetRangePointerValue(widget, event);
}

function finishSetRangePointerDrag(event) {
  const widget = event.currentTarget.closest(".setrange-widget");
  if (widget.dataset.dragging !== "true") {
    return;
  }
  delete widget.dataset.dragging;
  const shouldSave = Boolean(widget._setRangeDrag?.changed);
  delete widget._setRangeDrag;
  event.currentTarget.releasePointerCapture(event.pointerId);
  if (shouldSave) {
    saveSetRangeWidget(widget);
  }
}

function handleSetRangeKeyDown(event) {
  const widget = event.currentTarget.closest(".setrange-widget");
  const current = getSetRangeFromWidget(widget);
  if (!current) {
    return;
  }

  const keyDeltas = {
    ArrowLeft: -SET_RANGE_STEP_C,
    ArrowDown: -SET_RANGE_STEP_C,
    ArrowRight: SET_RANGE_STEP_C,
    ArrowUp: SET_RANGE_STEP_C,
  };
  const delta = keyDeltas[event.key];
  if (delta === undefined) {
    return;
  }
  event.preventDefault();

  const part = event.currentTarget.dataset.role || widget.dataset.selectedPart;
  if (part !== "low" && part !== "high") {
    return;
  }
  setSetRangeSelectedPart(widget, part);
  const options = getSetRangeWidgetOptions(widget, current);
  const nextRange = resizeSetRangeEndpoint(
    current.lowC,
    current.highC,
    part,
    current[`${part}C`] + delta,
    options,
  );
  if (nextRange) {
    renderSetRangeWidget(widget, nextRange.lowC, nextRange.highC);
    saveSetRangeWidget(widget);
  }
}

function setupSetRangeControls() {
  document.querySelectorAll(".setrange-widget").forEach((widget) => {
    updateSetRangeModeState(widget, widget.dataset.mode);
    const lowC = finiteNumber(widget.dataset.setRangeLowC);
    const highC = finiteNumber(widget.dataset.setRangeHighC);
    if (lowC !== null && highC !== null) {
      renderSetRangeWidget(widget, lowC, highC, widget.dataset.minRangeC);
    }
    setSetRangeSelectedPart(
      widget,
      widget.dataset.selectedPart === "high" ? "high" : "low",
    );

    widget
      .querySelectorAll("[data-role='low'], [data-role='high']")
      .forEach((element) => {
        element.addEventListener("pointerdown", handleSetRangePointerDown);
        element.addEventListener("pointermove", handleSetRangePointerMove);
        element.addEventListener("pointerup", finishSetRangePointerDrag);
        element.addEventListener("pointercancel", finishSetRangePointerDrag);
        element.addEventListener("keydown", handleSetRangeKeyDown);
      });
  });
}

/**
 * Create an input element for editing notes.
 * @param {string} value - Initial input value
 * @returns {HTMLInputElement}
 */
function createNoteInput(value) {
  const input = document.createElement("input");
  input.type = "text";
  input.value = value;
  input.className = "note-input-edit";
  return input;
}

/**
 * Set up event handlers for note input field.
 * @param {HTMLInputElement} input - Input element
 * @param {HTMLElement} noteElement - Parent note element
 * @param {number} deviceId - Device ID
 * @param {string} originalText - Original text for cancel
 */
function setupNoteInputHandlers(input, noteElement, deviceId, originalText) {
  const saveNote = () => {
    const newText = input.value.trim();
    noteElement.classList.remove("editing");
    noteElement.textContent = newText;
    updateNote(deviceId, newText || null);
  };

  input.addEventListener("blur", saveNote);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      input.blur();
    } else if (e.key === "Escape") {
      e.preventDefault();
      noteElement.classList.remove("editing");
      noteElement.textContent = originalText;
    }
  });
}

// Refresh the rows in the fan control and temperature panel grid.
const refreshGridRows = () => {
  const now = Date.now();
  const secondsSinceRefresh = Math.floor((now - lastRefreshTime) / 1000);
  const secondsUntilRefresh = forceRefresh
    ? 0
    : REFRESH_INTERVAL - secondsSinceRefresh;

  // Check if total runtime exceeded
  if (now - start > RUNNING_MINUTES * 60 * 1000) {
    document.querySelector("#status").innerHTML = "stopped.";
    document.querySelector("#main-grid").innerHTML =
      "Please click <b>reload</b> to restart the grid.";
    return;
  }

  // Update countdown display if there is a #text-update field
  if (SHOW_REFRESH_COUNTDOWN) {
    document.querySelector("#next-update").innerHTML =
      secondsUntilRefresh <= 0
        ? "Refreshing..."
        : `Next refresh in ${secondsUntilRefresh} seconds`;
  }

  // If it's time to refresh, run the status api and update all of the temps, fan_speeds, and status columsn
  if (secondsUntilRefresh <= 0) {
    runStatusRefresh(() =>
      fetch("/api/v1/status", { method: "GET" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Status request failed (${response.status})`);
        }
        return response.json();
      })
      .then((data) => {
        if (DEBUG) {
          console.log("Status data received:", data);
        }

        // Update the tables with the new data
        const refreshDate = new Date();
        if (data.devices)
          for (const dev of data.devices) {
            updateDashboardAirQualityRowVisibility(dev, refreshDate);
            updateTemperatureCell(
              document.getElementById(`temp-${dev.device_id}`),
              dev.temp10x,
              dev,
            );
            updateTemperatureCell(
              document.getElementById(`fcu-temp-${dev.device_id}`),
              dev.temp10x,
              dev,
            );
            updateTemperatureCell(
              document.getElementById(`room-temp-${dev.device_id}`),
              dev.calculated_temp10x,
              null,
            );
            const roomHumidityCell = document.getElementById(
              `room-humidity-${dev.device_id}`,
            );
            if (roomHumidityCell) {
              const roomHumidity =
                dev.calculated_humidity === null ||
                dev.calculated_humidity === undefined
                  ? NaN
                  : Number(dev.calculated_humidity);
              roomHumidityCell.textContent = Number.isFinite(roomHumidity)
                ? String(Math.round(roomHumidity))
                : "--";
            }
            if (dev.device_type === "FCU" && dev.room_id != null) {
              window.dispatchEvent(
                new CustomEvent("roommetricschange", {
                  detail: {
                    roomId: dev.room_id,
                    calculatedTemp10x: dev.calculated_temp10x,
                    calculatedHumidity: dev.calculated_humidity,
                  },
                }),
              );
            }

            // Update humidity where available
            const humidityCell = document.getElementById(
              `humidity-${dev.device_id}`,
            );
            if (humidityCell) {
              const status = dev.status || {};
              let humidityValue = null;

              const h = status.humidity;
              if (h && typeof h === "object" && h.value != null) {
                // Airthings-style: { value, unit }
                humidityValue = parseFloat(h.value);
              } else if (typeof h === "number") {
                humidityValue = h;
              } else if (typeof h === "string" && h.trim() !== "") {
                humidityValue = parseFloat(h);
              } else if (status.RoomHumidity != null) {
                humidityValue = parseFloat(status.RoomHumidity);
              } else if (status.InletHumidity != null) {
                humidityValue = parseFloat(status.InletHumidity);
              } else if (
                status.attributes &&
                status.attributes.humidity != null
              ) {
                const ah = status.attributes.humidity;
                if (typeof ah === "number") {
                  humidityValue = ah;
                } else if (typeof ah === "string" && ah.trim() !== "") {
                  humidityValue = parseFloat(ah);
                }
              }

              if (
                humidityValue != null &&
                !Number.isNaN(humidityValue) &&
                Number.isFinite(humidityValue)
              ) {
                const rounded = Math.round(humidityValue);
                // Reuse the same staleness + tooltip logic as temperature.
                updateStalenessAndTooltip(humidityCell, dev);

                humidityCell.textContent = String(rounded);
                humidityCell.setAttribute("data-air-quality-value", rounded.toString());
                refreshAirQualityClass(humidityCell);
              } else {
                humidityCell.textContent = "--";
                humidityCell.removeAttribute("data-air-quality-value");
                refreshAirQualityClass(humidityCell);
              }
            }

            // Update illuminance where available
            const illumCell = document.getElementById(
              `illuminance-${dev.device_id}`,
            );
            if (illumCell) {
              const status = dev.status || {};
              let illumValue = null;

              const il = status.illuminance;
              if (typeof il === "number") {
                illumValue = il;
              } else if (typeof il === "string" && il.trim() !== "") {
                illumValue = parseFloat(il);
              } else if (
                status.attributes &&
                status.attributes.illuminance != null
              ) {
                const ail = status.attributes.illuminance;
                if (typeof ail === "number") {
                  illumValue = ail;
                } else if (typeof ail === "string" && ail.trim() !== "") {
                  illumValue = parseFloat(ail);
                }
              }

              if (
                illumValue != null &&
                !Number.isNaN(illumValue) &&
                Number.isFinite(illumValue)
              ) {
                const rounded = Math.round(illumValue * 10) / 10;
                // Reuse the same staleness + tooltip logic as temperature.
                updateStalenessAndTooltip(illumCell, dev);

                illumCell.textContent = `${rounded.toFixed(1)}`;
              } else {
                illumCell.textContent = "--";
              }
            }

            // Update air quality metrics (Airthings-style {value, unit} objects)
            const aqMetrics = [
              { key: "co2",               cellPrefix: "co2",   decimals: 0, unit: "" },
              { key: "voc",               cellPrefix: "voc",   decimals: 0, unit: "" },
              { key: "radonShortTermAvg", cellPrefix: "radon", decimals: 0, unit: "" },
              { key: "pm25",              cellPrefix: "pm25",  decimals: 1, unit: "" },
              { key: "pm1",               cellPrefix: "pm1",   decimals: 1, unit: "" },
            ];
            for (const { key, cellPrefix, decimals } of aqMetrics) {
              const aqCell = document.getElementById(`${cellPrefix}-${dev.device_id}`);
              if (!aqCell) continue;
              const status = dev.status || {};
              const raw = status[key];
              let val = null;
              if (raw != null && typeof raw === "object" && raw.value != null) {
                val = parseFloat(raw.value);
              } else if (typeof raw === "number") {
                val = raw;
              } else if (typeof raw === "string" && raw.trim() !== "") {
                val = parseFloat(raw);
              }
              if (val != null && !Number.isNaN(val) && Number.isFinite(val)) {
                updateStalenessAndTooltip(aqCell, dev);
                aqCell.setAttribute("data-air-quality-value", val.toString());
                if (key === "radonShortTermAvg") {
                  aqCell.setAttribute("data-radon-bqm3", val.toString());
                  aqCell.textContent = TemperatureUtils.formatRadon(val);
                } else {
                  aqCell.textContent = val.toFixed(decimals);
                }
                refreshAirQualityClass(aqCell);
              } else {
                aqCell.textContent = "--";
                aqCell.removeAttribute("data-air-quality-value");
                refreshAirQualityClass(aqCell);
              }
            }

            updateSetTempForDevice(dev);

            updateSetRangeForDevice(dev);

            updateModeControlForDevice(dev);

            // Update radio button selection based on drive and speed state.
            const radioId = fanRadioIdForDevice(
              dev,
              pendingFanRadioIds.get(dev.device_id)?.radioId,
            );
            if (radioId) {
              const radio = document.getElementById(radioId);
              if (radio) {
                radio.checked = true;
              } else {
                console.warn(
                  `Radio button not found for ${radioId}, device_id=${dev.device_id}`,
                );
              }
            }
            updateDeviceNotes(dev);
            updateDeviceDisplayName(dev);
            updateDeviceNameTooltip(dev);
            updateRulesDisabledBadge(dev);
            updateDisableForCell(dev);
          }
        updateTableUpdateSummaries(data.devices || [], refreshDate);

        // Update last refresh time
        const lr = document.getElementById("last-refresh");
        if (lr) {
          lr.textContent = "Last Refresh: " + asctime(new Date());
        }

        // Update the refresh time
        lastRefreshTime = now;
        forceRefresh = false;
      })
      .catch((error) => {
        console.error("Error refreshing leaderboard:", error);
        // Still update the refresh time on error to prevent rapid retries
        lastRefreshTime = now;
      }),
    );
  }
  setTimeout(refreshGridRows, 1000); // Schedule next check in 1 second
};

/* This loads weather and starts the refresh cycle. */
async function loadWeatherAndStartRefresh() {
  console.log("Running loadWeatherAndStartRefresh()");
  try {
    fetch("api/v1/weather", { method: "GET" })
      .then((response) => response.json())
      .then((data) => {
        console.log("Weather data received:", data);

        const aqiValueElement = document.getElementById("aqi-value");
        const aqiNameElement = document.getElementById("aqi-name");

        if (aqiValueElement && aqiNameElement) {
          if (data.aqi.error) {
            aqiValueElement.textContent = "Error";
            aqiNameElement.textContent = data.aqi.error;
          } else {
            aqiValueElement.textContent = data.aqi.value;
            aqiNameElement.textContent = data.aqi.name;
            aqiNameElement.style.backgroundColor = data.aqi.color;
          }
        }
        // Display weather information if available
        if (data.weather) {
          displayWeather(data.weather);
        }
      });

    // Start the refresh cycle
    refreshGridRows();
  } catch (e) {
    console.error("Error in loadWeatherAndStartRefresh():", e);
  }
}

/**
 * Update device notes display.
 * @param {Object} dev - Device data object
 */
function updateDeviceNotes(dev) {
  if (dev.notes === undefined) {
    return;
  }
  const cell = document.getElementById(`notes-${dev.device_id}`);
  if (cell && !cell.classList.contains("editing")) {
    cell.textContent = dev.notes || "";
  }
}

function updateDeviceDisplayName(dev) {
  if (dev.display_name === undefined && dev.device_name === undefined) {
    return;
  }
  const labels = document.querySelectorAll(
    `.device-name-context[data-device-id="${dev.device_id}"]`,
  );
  if (labels.length === 0) {
    return;
  }
  const existingDeviceName = labels[0].dataset.deviceName || "";
  const deviceName = dev.device_name || existingDeviceName;
  const displayName = dev.display_name || deviceName;
  const deviceType =
    dev.device_type === undefined ? labels[0].dataset.deviceType : dev.device_type;
  const rulesEnabled =
    dev.rules_enabled === undefined
      ? labels[0].dataset.rulesEnabled
      : dev.rules_enabled;
  applyDeviceDisplayName(
    dev.device_id,
    deviceName,
    displayName,
    deviceType,
    rulesEnabled,
  );
}

// Pending optimistic writes for the "Disable for" column, keyed by device_id.
// While an entry is present, the cell shows the local target value and the
// refresh loop skips server updates for that device until the debounced POST
// resolves. `seq` disambiguates so a late-resolving older POST can't clear an
// entry belonging to a newer click.
const pendingDisableWrites = new Map();
const DISABLE_WRITE_DEBOUNCE_MS = 400;
let disableWriteSeq = 0;

/**
 * Initialize −/+ buttons for the "Disable for" column. Snaps the *remaining
 * duration* (in minutes, matching the cell display) to the next/previous
 * 30-min multiple; once aligned, each click moves by exactly 30 min. The
 * display updates immediately; the server POST is debounced so rapid clicks
 * coalesce into a single write.
 */
function setupDisableForControls() {
  document.querySelectorAll(".disable-btn").forEach((button) => {
    button.addEventListener("click", function () {
      const deviceId = parseInt(this.getAttribute("data-device-id"));
      const delta = parseInt(this.getAttribute("data-delta") || "0");
      const display = document.getElementById(`disable-display-${deviceId}`);
      if (!display) {
        return;
      }
      const currentAttr = display.getAttribute("data-disabled-until");
      const current = currentAttr ? parseInt(currentAttr) : 0;
      if (!current) {
        return;
      }
      const now = Math.floor(Date.now() / 1000);
      const remainingMin = Math.ceil((current - now) / 60);
      let newMin;
      if (delta > 0) {
        newMin = Math.ceil((remainingMin + 1) / 30) * 30;
      } else {
        newMin = Math.floor((remainingMin - 1) / 30) * 30;
      }
      const next = newMin > 0 ? now + newMin * 60 : 0;

      // Optimistically render, then debounce the POST.
      renderDisableCell(deviceId, next);
      const existing = pendingDisableWrites.get(deviceId);
      if (existing) {
        clearTimeout(existing.timer);
      }
      const seq = ++disableWriteSeq;
      const timer = setTimeout(() => {
        setDeviceDisabledUntil(deviceId, next, seq);
      }, DISABLE_WRITE_DEBOUNCE_MS);
      pendingDisableWrites.set(deviceId, { timer, seq });
    });
  });
}

/**
 * Update the "Disable for" cell from server data, unless a local optimistic
 * write is pending for this device (in which case we keep showing the local
 * target until the debounced POST resolves).
 */
function updateDisableForCell(dev) {
  if (pendingDisableWrites.has(dev.device_id)) {
    return;
  }
  renderDisableCell(dev.device_id, dev.disabled_until || 0);
}

async function setDeviceDisabledUntil(deviceId, disabledUntil, seq) {
  try {
    await fetch("/api/v1/set_device_disabled_until", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        disabled_until: disabledUntil,
      }),
    });
  } catch (e) {
    console.error("Failed to set device disabled_until:", e);
    alert("Error setting disable timer.");
  } finally {
    const entry = pendingDisableWrites.get(deviceId);
    if (entry && entry.seq === seq) {
      pendingDisableWrites.delete(deviceId);
    }
    forceRefresh = true;
  }
}

function clearPendingDisableWrite(deviceId) {
  const existing = pendingDisableWrites.get(deviceId);
  if (existing?.timer) {
    clearTimeout(existing.timer);
  }
  pendingDisableWrites.delete(deviceId);
}

function hideRulesDisabledBadge(deviceId) {
  const badge = document.getElementById(`rules-disabled-${deviceId}`);
  if (!badge) {
    return;
  }
  badge.classList.add("hidden");
  badge.replaceChildren();
  badge.removeAttribute("title");
}

function enableRulesForDevice(deviceId) {
  clearPendingDisableWrite(deviceId);
  const seq = ++disableWriteSeq;
  pendingDisableWrites.set(deviceId, { seq });
  renderDisableCell(deviceId, 0);
  hideRulesDisabledBadge(deviceId);
  setDeviceDisabledUntil(deviceId, 0, seq);
}

function setupRulesDisabledBadgeControls() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".rules-disabled-clear");
    if (!button) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const deviceId = parseInt(button.dataset.deviceId, 10);
    if (Number.isNaN(deviceId)) {
      return;
    }
    enableRulesForDevice(deviceId);
  });
}

/**
 * Render the disable-for cell for a given device_id and disabled_until (epoch sec).
 * @param {number} deviceId
 * @param {number} until - 0 means re-enabled (show dash, hide buttons).
 */
function renderDisableCell(deviceId, until) {
  const display = document.getElementById(`disable-display-${deviceId}`);
  if (!display) {
    return;
  }
  const cell = document.getElementById(`disable-for-${deviceId}`);
  const buttons = cell ? cell.querySelectorAll(".disable-btn") : [];
  const now = Math.floor(Date.now() / 1000);
  const secondsRemaining = (until || 0) - now;
  if (secondsRemaining <= 0) {
    cell?.classList.remove("rules-disabled-active");
    display.textContent = "—";
    display.removeAttribute("data-disabled-until");
    buttons.forEach((b) => b.classList.add("hidden"));
    return;
  }
  const totalMinutes = Math.ceil(secondsRemaining / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  display.textContent = `${hours}:${String(minutes).padStart(2, "0")}`;
  display.setAttribute("data-disabled-until", String(until));
  cell?.classList.add("rules-disabled-active");
  buttons.forEach((b) => b.classList.remove("hidden"));
}

/**
 * Update rules disabled badge display.
 * @param {Object} dev - Device data object
 */
function updateRulesDisabledBadge(dev) {
  const badge = document.getElementById(`rules-disabled-${dev.device_id}`);
  if (!badge) {
    return;
  }

  const now = Math.floor(Date.now() / 1000);
  if (dev.disabled_until && dev.disabled_until > now) {
    const dt = new Date(dev.disabled_until * 1000);
    const hoursRemaining = Math.ceil((dev.disabled_until - now) / 3600);
    const tooltipText = `Rules disabled until ${asctime(dt)} (${hoursRemaining} hour${hoursRemaining !== 1 ? "s" : ""})`;
    const label = document.createElement("span");
    label.textContent = "rules disabled";
    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "rules-disabled-clear";
    clearButton.dataset.deviceId = String(dev.device_id);
    clearButton.setAttribute("aria-label", "Enable rules for this FCU");
    clearButton.setAttribute("title", "Enable rules for this FCU");
    clearButton.textContent = "[x]";
    badge.replaceChildren(label, " ", clearButton);
    badge.setAttribute("title", tooltipText);
    badge.classList.remove("hidden");
  } else {
    hideRulesDisabledBadge(dev.device_id);
  }
}

// Browser-only wiring (skipped under Node.js test environment).
if (typeof window !== "undefined") {
  // Make refreshGridRows and displayWeather available globally for temperature unit changes
  window.refreshGridRows = refreshGridRows;
  window.displayWeather = displayWeather;
  window.getCurrentWeatherData = function () {
    return currentWeatherData;
  };

  window.addEventListener("DOMContentLoaded", function () {
    setupMatrixListeners();
    loadWeatherAndStartRefresh();
  });
  window.addEventListener("roomassignmentchange", () => {
    forceRefresh = true;
    refreshOpenFcuTempSources();
  });
}

// Node.js export for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    collectFcuTempSourceChanges,
    autoSetTempRangeForDevice,
    compactAgeFromSeconds,
    clearPendingFanChange,
    createSingleFlight,
    dashboardAirQualityDeviceIsActive,
    deviceDisplayNameChanged,
    deviceLabelWithIcon,
    deviceDisplayNamePatchBody,
    deviceRulesEnabledValue,
    deviceUpdateText,
    deviceUpdateTooltipText,
    deviceUpdateTimestampSeconds,
    ensureModeSelectOption,
    fanRadioIdForDevice,
    FCU_MODE_OPTIONS,
    fcuTempSourcesTitle,
    isAutoOperationMode,
    isFanOperationMode,
    setTempDisabledTooltip,
    modeLabelForDevice,
    modeValueForDevice,
    enableRulesForDevice,
    markRangePending,
    markSingleSetTempPending,
    normalizeSetRange,
    oldestUpdateTimestampForTable,
    parseFcuTempSourceMultiplier,
    pendingRangeUpdateDecision,
    pendingSingleSetTempUpdateDecision,
    renderDisableCell,
    renderAutoSetTempRange,
    refreshOpenFcuTempSources,
    resizeSetRangeEndpoint,
    saveAutoSetTempWidget,
    saveFcuTempSourceMultipliers,
    setRangePartFromPointerTarget,
    setAutoSetTempUnavailable,
    updateSetRangeModeState,
    sortedFcuTempSources,
    tableUpdateSummaryText,
    updateSetTempForDevice,
    updateTemperatureCell,
  };
}
