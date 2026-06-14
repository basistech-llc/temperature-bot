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
  const status = dev.status || {};
  const rawMode = dev.mode || status.Mode;
  if (rawMode == null || rawMode === "") {
    return "--";
  }
  const rawModeString = String(rawMode);
  return AE200_MODE_LABELS[rawModeString.toUpperCase()] || rawModeString;
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

  // Add event listeners for "Disable for" ± controls
  setupDisableForControls();
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
            if (dev.temp10x) {
              const cell = document.getElementById(`temp-${dev.device_id}`);
              if (cell) {
                const tempC = dev.temp10x / 10;
                // Store original Celsius value in data attribute for instant conversion
                cell.setAttribute("data-temp-c", tempC.toString());

                // Apply shared staleness + tooltip behavior
                updateStalenessAndTooltip(cell, dev);

                // Display temperature; omit unit when header already shows it
                const includeUnit = !cell.classList.contains("temp-display-no-unit");
                cell.innerHTML = TemperatureUtils.formatTemperature(tempC, includeUnit);
              }
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

            const modeCell = document.getElementById(`mode-${dev.device_id}`);
            if (modeCell) {
              const status = dev.status || {};
              const rawMode = dev.mode || status.Mode;
              modeCell.textContent = modeLabelForDevice(dev);
              if (rawMode) {
                modeCell.setAttribute("title", `AE-200 Mode: ${rawMode}`);
              } else {
                modeCell.removeAttribute("title");
              }
            }

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
  module.exports = { fanRadioIdForDevice, modeLabelForDevice };
}
