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
let lastRefreshTime = 0;
const AE200_MODE_LABELS = {
  COOL: "Cool",
  HEAT: "Heat",
  AUTO: "Auto",
  DRY: "Dry",
  FAN: "Fan",
  LC_AUTO: "Auto",
};
const FCU_MODE_OPTIONS = ["FAN", "COOL", "HEAT"];
const FCU_MODE_DEVICE_ID_KEY = "device_id";
const FCU_MODE_MODE_KEY = "mode";
const SET_RANGE_TRACK_MIN_C = 10;
const SET_RANGE_TRACK_MAX_C = 30;
const SET_RANGE_STEP_C = 0.5;
const DEFAULT_MIN_SET_RANGE_C = 3.0;
const SET_RANGE_DEVICE_ID_KEY = "device_id";
const SET_RANGE_LOW_KEY = "set_range_low_c";
const SET_RANGE_HIGH_KEY = "set_range_high_c";

// Refresh logic
var start = Date.now();
var forceRefresh = false;

// Store weather data globally so it can be re-rendered when unit changes
let currentWeatherData = null;

////////////////////////////////////////////////////////////////
// Shared helpers

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
 * @returns {string|null} The id of the radio to select, or null if undetermined.
 */
function fanRadioIdForDevice(dev) {
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
    cell.setAttribute("title", `Last updated: ${dev.age} ago`);
  }

  // Apply color class based on staleness
  cell.classList.remove("temp-stale");
  if (isStale) {
    cell.classList.add("temp-stale");
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

function moveSetRange(lowC, highC, deltaC, options = {}) {
  const opts = setRangeOptions(options);
  const current = normalizeSetRange(lowC, highC, opts);
  if (!current) {
    return null;
  }

  const width = current.highC - current.lowC;
  let low = current.lowC + deltaC;
  if (low < opts.trackMinC) {
    low = opts.trackMinC;
  }
  if (low + width > opts.trackMaxC) {
    low = opts.trackMaxC - width;
  }
  return {
    lowC: roundTempC(low),
    highC: roundTempC(low + width),
  };
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

function setFcuTempSourcesMessage(popup, message, isError = false) {
  const messageElement = popup.querySelector("[data-role='message']");
  if (!messageElement) {
    return;
  }
  messageElement.textContent = message || "";
  messageElement.classList.toggle("error", isError);
}

function closeFcuTempSourcesPopup() {
  const popup = document.getElementById("fcu-temp-sources-popup");
  if (popup) {
    popup.classList.add("hidden");
  }
}

function renderFcuTempSources(popup, data, updateUrl) {
  const tbody = popup.querySelector("[data-role='sources-body']");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";

  if (!data.sources || data.sources.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = "No temperature-reporting sources found.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  for (const source of data.sources) {
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
    input.type = "number";
    input.min = "0";
    input.step = "0.1";
    input.value = String(source.multiplier);
    input.className = "fcu-temp-source-weight";
    input.setAttribute("aria-label", `Weight for ${source.device_name}`);
    input.dataset.fcuDeviceId = String(data.fcu_device_id);
    input.dataset.sourceDeviceId = String(source.source_device_id);
    input.dataset.updateUrl = updateUrl;
    input.addEventListener("change", saveFcuTempSourceMultiplier);
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

  popup.classList.remove("hidden");
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
    renderFcuTempSources(popup, data, updateUrl);
    setFcuTempSourcesMessage(popup, "");
  } catch (error) {
    console.error("Failed to load FCU temperature sources:", error);
    setFcuTempSourcesMessage(popup, error.message, true);
  }
}

async function saveFcuTempSourceMultiplier(event) {
  const input = event.currentTarget;
  const popup = document.getElementById("fcu-temp-sources-popup");
  const multiplier = parseFloat(input.value);
  if (!popup || !Number.isFinite(multiplier) || multiplier < 0) {
    if (popup) {
      setFcuTempSourcesMessage(popup, "Weight must be a nonnegative number.", true);
    }
    return;
  }

  input.disabled = true;
  setFcuTempSourcesMessage(popup, "Saving...");
  try {
    const response = await fetch(input.dataset.updateUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fcu_device_id: parseInt(input.dataset.fcuDeviceId, 10),
        source_device_id: parseInt(input.dataset.sourceDeviceId, 10),
        multiplier: multiplier,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to save weight.");
    }
    renderFcuTempSources(popup, data, input.dataset.updateUrl);
    setFcuTempSourcesMessage(popup, "Saved.");
    forceRefresh = true;
  } catch (error) {
    console.error("Failed to save FCU temperature source multiplier:", error);
    setFcuTempSourcesMessage(popup, error.message, true);
  } finally {
    input.disabled = false;
  }
}

////////////////////////////////////////////////////////////////
// Weather display functions
function displayWeather(weatherInfo) {
  console.log("displayWeather called with:", weatherInfo);
  const weatherDiv = document.getElementById("weather");
  if (!weatherDiv || !weatherInfo) {
    console.log(
      "Early return - weatherDiv:",
      !!weatherDiv,
      "weatherInfo:",
      !!weatherInfo,
    );
    return;
  }

  let html = "";
  // Add weather content
  if (weatherInfo.current) {
    const current = weatherInfo.current;
    const temp = current.temperature
      ? `${TemperatureUtils.formatTemperature(current.temperature)} (Boston Logan Airport)`
      : "N/A";
    html += `<div><strong>Current:</strong> ${temp} `;
    if (current.icon) {
      html += ` <img src="${current.icon}" alt="weather icon" class="weather-icon">`;
    }
    html += `${current.conditions}</div>`;
    console.log("Added current weather to HTML");
  }

  // Forecast
  if (weatherInfo.forecast && weatherInfo.forecast.length > 0) {
    html += `<div><strong>Forecast for CALA:</strong></div>`;
    weatherInfo.forecast.forEach((period) => {
      // Convert forecast temp from Fahrenheit to Celsius first, then apply unit preference
      const tempF = parseFloat(period.temperature);
      const tempC = TemperatureUtils.fahrenheitToCelsius(tempF);
      const formattedTemp = TemperatureUtils.formatTemperature(tempC);
      html += `<div>${period.time} ${formattedTemp} `;
      if (period.icon) {
        html += ` <img src="${period.icon}" alt="weather icon" class="weather-icon">`;
      }
      html += `${period.conditions}</div>`;
    });
    console.log("Added forecast to HTML");
  }
  weatherDiv.innerHTML = html;
  // Store weather data for later re-rendering
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
    console.log("Set drive: result=", result);
    forceRefresh = true;
  } catch (e) {
    console.error("Failed to set fan_speed:", e);
    alert("Error setting fan_speed.");
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
    console.log("Set fan_speed: result=", result);
    forceRefresh = true;
  } catch (e) {
    console.error("Failed to set fan_speed:", e);
    alert("Error setting fan_speed.");
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
    radio.addEventListener("change", function () {
      const deviceId = parseInt(this.getAttribute("x-data-device-id"));
      const fan_speed = parseInt(this.getAttribute("x-data-fan_speed"));

      // Off button (0): turn off drive
      if (fan_speed === 0) {
        setDrive(deviceId, 0);
      }
      // Speed buttons: turn on drive AND set speed
      else {
        Promise.all([
          setDrive(deviceId, 1),
          setFanSpeed(deviceId, fan_speed),
        ]).catch((error) => {
          console.error("Error setting drive and speed:", error);
        });
      }
    });
  });

  // Add event listeners for editable notes
  setupEditableNotes();

  // Add event listeners for set temperature controls
  setupSetTempControls();

  // Add event listeners for FCU set ranges.
  setupSetRangeControls();

  // Add event listeners for FCU operation modes.
  setupModeControls();

  // Add event listeners for "Disable for" ± controls
  setupDisableForControls();

  // Add event listeners for calculated room-temperature source weights.
  setupFcuTempSourcePopupControls();
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
      setDeviceMode(deviceId, mode)
        .then((result) => {
          const savedMode = result.mode || mode;
          ensureModeSelectOption(this, savedMode);
          this.value = savedMode;
          this.dataset.currentMode = savedMode;
        })
        .catch(() => {
          ensureModeSelectOption(this, previousMode);
          this.value = previousMode;
          this.dataset.currentMode = previousMode;
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
  document.querySelectorAll(".room-temp-link").forEach((cell) => {
    cell.addEventListener("click", function (event) {
      event.preventDefault();
      loadFcuTempSourcesForCell(this);
    });
  });

  const popup = document.getElementById("fcu-temp-sources-popup");
  if (!popup) {
    return;
  }
  popup
    .querySelectorAll("[data-action='close-fcu-temp-sources']")
    .forEach((button) => {
      button.addEventListener("click", closeFcuTempSourcesPopup);
    });
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

      // Clamp to a reasonable range in UI units
      const minUI = useFahrenheit ? 50 : 10; // ~10°C / 50°F
      const maxUI = useFahrenheit ? 86 : 30; // ~30°C / 86°F
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

      // Send to backend in Celsius
      setDeviceSetTemp(deviceId, newC);
    });
  });
}

/**
 * Call backend API to set device set temperature in Celsius.
 * @param {number} deviceId
 * @param {number} setTempC
 */
async function setDeviceSetTemp(deviceId, setTempC) {
  try {
    const response = await fetch("/api/v1/set_temp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, set_temp_c: setTempC }),
    });
    const result = await response.json();
    if (DEBUG) {
      console.log("Set temp result:", result);
    }
    // Force data refresh to pick up canonical values from AE-200
    forceRefresh = true;
  } catch (e) {
    console.error("Failed to set temperature:", e);
    alert("Error setting temperature.");
  }
}

function getSetRangeWidgetOptions(widget, range = null) {
  const minRangeC = finiteNumber(
    widget.dataset.minRangeC,
    DEFAULT_MIN_SET_RANGE_C,
  );
  let trackMinC = SET_RANGE_TRACK_MIN_C;
  let trackMaxC = SET_RANGE_TRACK_MAX_C;
  if (range) {
    trackMinC = Math.min(trackMinC, range.lowC);
    trackMaxC = Math.max(trackMaxC, range.highC);
  }
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
    .querySelectorAll("[data-role='low'], [data-role='high'], [data-role='middle']")
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
    trackMinC: Math.min(SET_RANGE_TRACK_MIN_C, finiteNumber(lowC, SET_RANGE_TRACK_MIN_C)),
    trackMaxC: Math.max(SET_RANGE_TRACK_MAX_C, finiteNumber(highC, SET_RANGE_TRACK_MAX_C)),
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
      forceRefresh = true;
    })
    .catch((error) => {
      console.error("Failed to save set range:", error);
      alert("Error setting range.");
    })
    .finally(() => {
      delete widget.dataset.saving;
    });
}

function updateSetRangeForDevice(dev) {
  const widget = document.getElementById(`setrange-widget-${dev.device_id}`);
  if (!widget || widget.dataset.dragging === "true") {
    return;
  }
  if (
    dev.set_range_low_c === undefined ||
    dev.set_range_high_c === undefined
  ) {
    setSetRangeUnavailable(widget);
    return;
  }
  renderSetRangeWidget(
    widget,
    dev.set_range_low_c,
    dev.set_range_high_c,
    dev.min_set_range_c,
  );
}

function applySetRangePointerValue(widget, event) {
  const drag = widget._setRangeDrag;
  const current = getSetRangeFromWidget(widget);
  if (!drag || !current) {
    return;
  }

  const options = getSetRangeWidgetOptions(widget, current);
  let nextRange;
  if (drag.part === "middle") {
    const currentPointerC = pointerEventToRangeTemp(widget, event);
    nextRange = moveSetRange(
      drag.startLowC,
      drag.startHighC,
      currentPointerC - drag.startPointerC,
      options,
    );
  } else {
    nextRange = resizeSetRangeEndpoint(
      current.lowC,
      current.highC,
      drag.part,
      pointerEventToRangeTemp(widget, event),
      options,
    );
  }
  if (nextRange && !setRangesEqual(current, nextRange)) {
    drag.changed = true;
    renderSetRangeWidget(widget, nextRange.lowC, nextRange.highC);
  }
}

function setRangePartFromPointerTarget(widget, event) {
  const role = event.target.dataset.role;
  if (role === "low" || role === "high" || role === "middle") {
    return role;
  }

  const current = getSetRangeFromWidget(widget);
  if (!current) {
    return "middle";
  }
  const pointerC = pointerEventToRangeTemp(widget, event);
  return Math.abs(pointerC - current.lowC) <= Math.abs(pointerC - current.highC)
    ? "low"
    : "high";
}

function handleSetRangePointerDown(event) {
  const widget = event.currentTarget.closest(".setrange-widget");
  const current = getSetRangeFromWidget(widget);
  if (!current) {
    return;
  }
  event.preventDefault();

  const part = setRangePartFromPointerTarget(widget, event);
  setSetRangeSelectedPart(widget, part);
  if (typeof event.target.focus === "function") {
    event.target.focus();
  }

  widget.dataset.dragging = "true";
  widget._setRangeDrag = {
    part,
    changed: false,
    startLowC: current.lowC,
    startHighC: current.highC,
    startPointerC: pointerEventToRangeTemp(widget, event),
  };
  event.currentTarget.setPointerCapture(event.pointerId);

  if (event.target.dataset.role === "track") {
    applySetRangePointerValue(widget, event);
  }
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
  setSetRangeSelectedPart(widget, part);
  const options = getSetRangeWidgetOptions(widget, current);
  const nextRange =
    part === "middle"
      ? moveSetRange(current.lowC, current.highC, delta, options)
      : resizeSetRangeEndpoint(
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
    const lowC = finiteNumber(widget.dataset.setRangeLowC);
    const highC = finiteNumber(widget.dataset.setRangeHighC);
    if (lowC !== null && highC !== null) {
      renderSetRangeWidget(widget, lowC, highC, widget.dataset.minRangeC);
    }
    setSetRangeSelectedPart(widget, widget.dataset.selectedPart || "middle");

    const track = widget.querySelector(".setrange-track");
    track.addEventListener("pointerdown", handleSetRangePointerDown);
    track.addEventListener("pointermove", handleSetRangePointerMove);
    track.addEventListener("pointerup", finishSetRangePointerDrag);
    track.addEventListener("pointercancel", finishSetRangePointerDrag);
    widget
      .querySelectorAll("[data-role='low'], [data-role='high'], [data-role='middle']")
      .forEach((element) => {
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
    fetch("/api/v1/status", { method: "GET" })
      .then((response) => response.json())
      .then((data) => {
        if (DEBUG) {
          console.log("Status data received:", data);
        }

        // Update the tables with the new data
        if (data.devices)
          for (const dev of data.devices) {
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
                const rounded = Math.round(humidityValue * 10) / 10;
                // Reuse the same staleness + tooltip logic as temperature.
                updateStalenessAndTooltip(humidityCell, dev);

                humidityCell.textContent = `${rounded.toFixed(1)}`;
              } else {
                humidityCell.textContent = "--";
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
                if (key === "radonShortTermAvg") {
                  aqCell.setAttribute("data-radon-bqm3", val.toString());
                  aqCell.textContent = TemperatureUtils.formatRadon(val);
                } else {
                  aqCell.textContent = val.toFixed(decimals);
                }
              } else {
                aqCell.textContent = "--";
              }
            }

            // Update set temperature (from AE-200 status) where available
            const setTempCell = document.getElementById(
              `settemp-${dev.device_id}`,
            );
            const setTempDisplay = document.getElementById(
              `settemp-display-${dev.device_id}`,
            );

            if (setTempCell && setTempDisplay) {
              const status = dev.status || {};
              const rawSetTemp = status.SetTemp;

              if (rawSetTemp !== undefined && rawSetTemp !== "") {
                const setTempValue = parseFloat(rawSetTemp);
                if (!Number.isNaN(setTempValue)) {
                  // AE-200 SetTemp is reported in Celsius
                  const setTempC = setTempValue;
                  // Store Celsius value for UI conversions and adjustments
                  setTempCell.setAttribute("data-temp-c", setTempC.toString());
                  setTempDisplay.setAttribute(
                    "data-temp-c",
                    setTempC.toString(),
                  );
                  updateStalenessAndTooltip(setTempDisplay, dev);
                  setTempDisplay.textContent =
                    TemperatureUtils.formatTemperature(setTempC, false);
                } else {
                  setTempCell.removeAttribute("data-temp-c");
                  setTempDisplay.removeAttribute("data-temp-c");
                  setTempDisplay.textContent = "--";
                }
              } else {
                setTempCell.removeAttribute("data-temp-c");
                setTempDisplay.removeAttribute("data-temp-c");
                setTempDisplay.textContent = "--";
              }
            }

            updateSetRangeForDevice(dev);

            updateModeControlForDevice(dev);

            // Update radio button selection based on drive and speed state.
            const radioId = fanRadioIdForDevice(dev);
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
            updateRulesDisabledBadge(dev);
            updateDisableForCell(dev);
          }

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
      });
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

  if (dev.disabled_until) {
    const dt = new Date(dev.disabled_until * 1000);
    const now = Math.floor(Date.now() / 1000);
    const hoursRemaining = Math.ceil((dev.disabled_until - now) / 3600);
    const tooltipText = `Rules disabled until ${asctime(dt)} (${hoursRemaining} hour${hoursRemaining !== 1 ? "s" : ""})`;
    badge.textContent = "rules disabled";
    badge.setAttribute("title", tooltipText);
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
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
}

// Node.js export for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    ensureModeSelectOption,
    fanRadioIdForDevice,
    modeLabelForDevice,
    modeValueForDevice,
    moveSetRange,
    normalizeSetRange,
    resizeSetRangeEndpoint,
  };
}
