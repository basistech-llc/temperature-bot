// temperature_utils.js - Shared temperature conversion utilities
// Centralized temperature unit management and conversion functions

// Global temperature unit setting
let USE_FAHRENHEIT = false; // Default to Celsius

// Load temperature unit preference from localStorage on initialization
function loadTemperaturePreference() {
  const saved = localStorage.getItem("temperatureUnit");
  if (saved === "fahrenheit") {
    USE_FAHRENHEIT = true;
  } else if (saved === "celsius") {
    USE_FAHRENHEIT = false;
  }
  // If no saved preference or invalid value, keep default (Celsius)
}

// Save temperature unit preference to localStorage
function saveTemperaturePreference() {
  try {
    localStorage.setItem(
      "temperatureUnit",
      USE_FAHRENHEIT ? "fahrenheit" : "celsius",
    );
  } catch (error) {
    console.warn(
      "Failed to save temperature preference to localStorage:",
      error,
    );
  }
}

/**
 * Convert Celsius to Fahrenheit
 * @param {number} celsius - Temperature in Celsius
 * @returns {number} Temperature in Fahrenheit
 */
function celsiusToFahrenheit(celsius) {
  return (celsius * 9) / 5 + 32;
}

/**
 * Convert Fahrenheit to Celsius
 * @param {number} fahrenheit - Temperature in Fahrenheit
 * @returns {number} Temperature in Celsius
 */
function fahrenheitToCelsius(fahrenheit) {
  return ((fahrenheit - 32) * 5) / 9;
}

/**
 * Format temperature value with appropriate unit
 * @param {number} tempC - Temperature in Celsius
 * @param {boolean} [includeUnit=true] - Whether to include unit symbol
 * @returns {string} Formatted temperature string
 */
function formatTemperature(tempC, includeUnit = true) {
  const temp = USE_FAHRENHEIT ? celsiusToFahrenheit(tempC) : tempC;
  const unit = getTemperatureUnit();
  return includeUnit ? `${temp.toFixed(1)}${unit}` : temp.toFixed(1);
}

/**
 * Get the current temperature unit symbol
 * @returns {string} '°C' or '°F'
 */
function getTemperatureUnit() {
  return USE_FAHRENHEIT ? "°F" : "°C";
}

/**
 * Set the temperature unit preference
 * @param {boolean} useFahrenheit - True for Fahrenheit, false for Celsius
 */
function setTemperatureUnit(useFahrenheit) {
  USE_FAHRENHEIT = useFahrenheit;
  saveTemperaturePreference();
  updateTemperatureToggleUI();
}

/**
 * Get the current temperature unit preference
 * @returns {boolean} True if using Fahrenheit, false if using Celsius
 */
function getTemperatureUnitPreference() {
  return USE_FAHRENHEIT;
}

/**
 * Update the temperature toggle UI to reflect current state
 */
function updateTemperatureToggleUI() {
  const toggle = document.getElementById("temp-unit-toggle");
  const labels = document.querySelectorAll(".temp-unit-label");

  if (toggle && labels.length === 2) {
    // Set checkbox state
    toggle.checked = USE_FAHRENHEIT;

    // Update label states
    if (USE_FAHRENHEIT) {
      // Fahrenheit is active
      labels[0].classList.remove("active"); // °C
      labels[1].classList.add("active"); // °F
    } else {
      // Celsius is active
      labels[0].classList.add("active"); // °C
      labels[1].classList.remove("active"); // °F
    }
  }

  updateAqTempHeader();
  updateRadonHeaders();
}

/** Thresholds for elevated/problem tooltip (Celsius); converted to °F when preference is Fahrenheit. */
const AQ_TEMP_THRESHOLDS_C = { lowElevated: 18, highElevated: 20, lowComfort: 25, highComfort: 27 };

/** Radon thresholds in Bq/m³; converted to pCi/L when preference is Fahrenheit (US units). */
const RADON_THRESHOLDS_BQM3 = { fair: 75, poor: 150 };
const BQM3_TO_PCIL = 37;

/**
 * Format radon value with appropriate unit conversion.
 * US users (Fahrenheit) see pCi/L; others see Bq/m³.
 * @param {number} bqm3 - Radon value in Bq/m³
 * @returns {string} Formatted radon string
 */
function formatRadon(bqm3) {
  if (USE_FAHRENHEIT) {
    return (bqm3 / BQM3_TO_PCIL).toFixed(1);
  }
  return Math.round(bqm3).toString();
}

/**
 * Get the current radon unit label.
 * @returns {string} 'pCi/L' or 'Bq/m³'
 */
function getRadonUnit() {
  return USE_FAHRENHEIT ? "pCi/L" : "Bq/m³";
}

/**
 * Update AQ column headers: set unit label text and tooltip on each matching element.
 * @param {string[]} labelIds - DOM IDs of the <small> unit-label elements
 * @param {string} unitText - Unit string to display (e.g. "°C", "pCi/L")
 * @param {string} titleText - Tooltip text for the parent <th>
 */
function updateAqColumnHeader(labelIds, unitText, titleText) {
  for (const id of labelIds) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.textContent = unitText;
    const th = el.closest("th");
    if (th) th.title = titleText;
  }
}

function updateAqTempHeader() {
  const { lowElevated, highElevated, lowComfort, highComfort } = AQ_TEMP_THRESHOLDS_C;
  let title;
  if (USE_FAHRENHEIT) {
    const lE = Math.round(celsiusToFahrenheit(lowElevated));
    const hE = Math.round(celsiusToFahrenheit(highElevated));
    const lC = Math.round(celsiusToFahrenheit(lowComfort));
    const hC = Math.round(celsiusToFahrenheit(highComfort));
    title =
      "Temperature. Unit follows site C/F toggle.\n" +
      `Elevated: ${lE}–${hE} or ${lC}–${hC} °F.\n` +
      `Problem: <${lE} or >${hC} °F.`;
  } else {
    title =
      "Temperature. Unit follows site C/F toggle.\n" +
      `Elevated: ${lowElevated}–${highElevated} or ${lowComfort}–${highComfort} °C.\n` +
      `Problem: <${lowElevated} or >${highComfort} °C.`;
  }
  updateAqColumnHeader(["aq-temp-unit-label", "aq-index-temp-unit-label", "erv-temp-unit-label", "fcu-temp-unit-label", "fcu-room-temp-unit-label", "fcu-settemp-unit-label", "fcu-setrange-unit-label"], getTemperatureUnit(), title);
}

function updateRadonHeaders() {
  const { fair, poor } = RADON_THRESHOLDS_BQM3;
  let title;
  if (USE_FAHRENHEIT) {
    const fP = (fair / BQM3_TO_PCIL).toFixed(1);
    const pP = (poor / BQM3_TO_PCIL).toFixed(1);
    title =
      "Short-term average radon level. Unit follows site C/F toggle.\n" +
      `Fair: >${fP} pCi/L.\n` +
      `Poor: >${pP} pCi/L.`;
  } else {
    title =
      "Short-term average radon level (Bq/m³).\n" +
      `Fair: >${fair}.\n` +
      `Poor: >${poor}.`;
  }
  updateAqColumnHeader(["aq-radon-unit-label", "aq-index-radon-unit-label"], getRadonUnit(), title);
}

/**
 * Updates every temperature display on the page to match the current unit preference.
 * @returns {void}
 */
function updateAllTemperatureDisplays() {
  // .temp-display: value from data-temp-c; .temp-display-no-unit omits unit (e.g. air quality table)
  const tempDisplays = document.querySelectorAll(".temp-display");
  tempDisplays.forEach((element) => {
    const tempC = parseFloat(element.getAttribute("data-temp-c"));
    if (!isNaN(tempC)) {
      const includeUnit = !element.classList.contains("temp-display-no-unit");
      element.textContent = formatTemperature(tempC, includeUnit);
    }
  });

  const tempCells = document.querySelectorAll('[id^="temp-"], [id^="fcu-temp-"], [id^="room-temp-"]');
  tempCells.forEach((element) => {
    const tempC = parseFloat(element.getAttribute("data-temp-c"));
    if (!isNaN(tempC)) {
      const includeUnit = !element.classList.contains("temp-display-no-unit");
      const currentHTML = element.innerHTML;
      const ageMatch = currentHTML.match(/<span class=['"]age['"]>\(([^)]+)\)<\/span>/);
      const age = ageMatch ? ageMatch[1] : null;
      element.innerHTML = formatTemperature(tempC, includeUnit) + (age ? ` <span class='age'>(${age})</span> ` : "");
    }
  });

  const setTempDisplays = document.querySelectorAll(".settemp-display");
  setTempDisplays.forEach((element) => {
    const tempC = parseFloat(element.getAttribute("data-temp-c"));
    if (!isNaN(tempC)) {
      element.textContent = formatTemperature(tempC, false);
    }
  });

  // Update weather displays
  // Re-render weather if it's available
  if (typeof window.getCurrentWeatherData === "function") {
    const weatherData = window.getCurrentWeatherData();
    if (weatherData && typeof window.displayWeather === "function") {
      window.displayWeather(weatherData);
    }
  }

  updateAqTempHeader();
  updateRadonHeaders();

  // Update radon displays to match current unit preference
  document.querySelectorAll(".radon-display").forEach((element) => {
    const bqm3 = parseFloat(element.getAttribute("data-radon-bqm3"));
    if (!isNaN(bqm3)) {
      element.textContent = formatRadon(bqm3);
    }
  });
}

/**
 * Initialize temperature utilities and UI
 * @returns {void}
 */
function initializeTemperatureUtils() {
  loadTemperaturePreference();
  updateTemperatureToggleUI();
  updateAllTemperatureDisplays();

  // Set up toggle switch event listener
  const toggle = document.getElementById("temp-unit-toggle");
  if (toggle) {
    toggle.addEventListener("change", function () {
      setTemperatureUnit(toggle.checked);
      updateAllTemperatureDisplays();

      if (typeof updateTempChart === "function") {
        updateTempChart();
      }
    });
  } else {
    console.warn("Temperature toggle element not found - toggle functionality disabled");
  }
}

// Make functions available globally (skip in Node.js test environment)
if (typeof window === "undefined") { var window = {}; }
window.TemperatureUtils = {
  celsiusToFahrenheit,
  fahrenheitToCelsius,
  formatTemperature,
  getTemperatureUnit,
  setTemperatureUnit,
  getTemperatureUnitPreference,
  updateAllTemperatureDisplays,
  initializeTemperatureUtils,
  loadTemperaturePreference,
  updateTemperatureToggleUI,
  formatRadon,
  getRadonUnit,
};

// Auto-initialize when DOM is ready (skip in Node.js test environment)
if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", initializeTemperatureUtils);
}

// Node.js export for testing
if (typeof module !== "undefined" && module.exports) {
  module.exports = { celsiusToFahrenheit, fahrenheitToCelsius, formatTemperature, formatRadon, getRadonUnit, getTemperatureUnit, _setUseFahrenheit: (v) => { USE_FAHRENHEIT = v; } };
}
