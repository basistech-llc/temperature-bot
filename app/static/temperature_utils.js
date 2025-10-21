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
}

/**
 * Update all temperature displays on the page
 * This function should be called after changing the temperature unit
 * @returns {void}
 */
function updateAllTemperatureDisplays() {
  // Update device log temperatures
  const tempDisplays = document.querySelectorAll(".temp-display");
  tempDisplays.forEach((element) => {
    const tempC = parseFloat(element.getAttribute("data-temp-c"));
    if (!isNaN(tempC)) {
      element.textContent = formatTemperature(tempC);
    }
  });

  // Update weather displays
  // This will be handled by the weather refresh cycle
}

/**
 * Initialize temperature utilities and UI
 * @returns {void}
 */
function initializeTemperatureUtils() {
  loadTemperaturePreference();
  updateTemperatureToggleUI();

  // Set up toggle switch event listener
  const toggle = document.getElementById("temp-unit-toggle");
  if (toggle) {
    toggle.addEventListener("change", function () {
      setTemperatureUnit(toggle.checked);
      updateAllTemperatureDisplays();

      // Trigger chart refresh if chart_support.js is loaded
      if (typeof updateTempChart === "function") {
        updateTempChart();
      }

      // Trigger main dashboard refresh if unit_speed.js is loaded
      if (typeof window.refreshGridRows === "function") {
        window.refreshGridRows();
      }
    });
  } else {
    console.warn("Temperature toggle element not found - toggle functionality disabled");
  }
}

// Make functions available globally
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
};

// Auto-initialize when DOM is ready
document.addEventListener("DOMContentLoaded", initializeTemperatureUtils);
