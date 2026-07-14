/**
 * Node.js tests for temperature/radon conversion utilities
 * Run with: node tests/test_temperature_utils.js
 */
const {
  celsiusToFahrenheit,
  fahrenheitToCelsius,
  formatTemperature,
  formatRadon,
  getRadonUnit,
  getTemperatureUnit,
  _setUseFahrenheit,
} = require("../app/static/temperature_utils.js");

let passed = 0;
let failed = 0;

function check(label, actual, expected) {
  if (actual === expected) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got "${actual}", expected "${expected}"`);
  }
}

// -- Temperature conversion --
check("0C -> 32F", celsiusToFahrenheit(0), 32);
check("100C -> 212F", celsiusToFahrenheit(100), 212);
check("32F -> 0C", fahrenheitToCelsius(32), 0);
check("212F -> 100C", fahrenheitToCelsius(212), 100);

// -- formatTemperature in Celsius mode --
_setUseFahrenheit(false);
check("formatTemp 20C with unit", formatTemperature(20), "20.0°C");
check("formatTemp 20C no unit", formatTemperature(20, false), "20.0");
check("getTemperatureUnit C", getTemperatureUnit(), "°C");

// -- formatTemperature in Fahrenheit mode --
_setUseFahrenheit(true);
check("formatTemp 0C as F", formatTemperature(0), "32°F");
check("formatTemp 20C as F", formatTemperature(20, false), "68");
check("getTemperatureUnit F", getTemperatureUnit(), "°F");

// -- Radon in Celsius (Bq/m3) mode --
_setUseFahrenheit(false);
check("formatRadon 100 Bq", formatRadon(100), "100");
check("formatRadon 150 Bq", formatRadon(150), "150");
check("formatRadon 74 Bq", formatRadon(74), "74");
check("getRadonUnit metric", getRadonUnit(), "Bq/m\u00b3");

// -- Radon in Fahrenheit (pCi/L) mode --
_setUseFahrenheit(true);
check("formatRadon 100 -> pCi/L", formatRadon(100), "2.7");
check("formatRadon 150 -> pCi/L", formatRadon(150), "4.1");
check("formatRadon 37 -> pCi/L", formatRadon(37), "1.0");
check("formatRadon 74 -> pCi/L", formatRadon(74), "2.0");
check("getRadonUnit US", getRadonUnit(), "pCi/L");

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
