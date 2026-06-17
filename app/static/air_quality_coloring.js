const AIR_QUALITY_THRESHOLDS_URL = "/static/air_quality_thresholds.json";
const AIR_QUALITY_CLASS_NAMES = ["air-good", "air-fair", "air-poor"];

let cachedAirQualityThresholds = null;
let pendingAirQualityThresholds = null;

function airQualityNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = parseFloat(value);
  return Number.isFinite(number) ? number : null;
}

function thresholdNumber(rule, name) {
  if (!Object.prototype.hasOwnProperty.call(rule, name)) {
    return null;
  }
  return airQualityNumber(rule[name]);
}

function airQualityClassForValue(metricName, value, thresholds) {
  const rule = thresholds ? thresholds[metricName] : null;
  const numericValue = airQualityNumber(value);
  if (!rule || numericValue === null) {
    return "";
  }

  const poorBelow = thresholdNumber(rule, "poorBelow");
  if (poorBelow !== null && numericValue < poorBelow) {
    return "air-poor";
  }

  const poorAbove = thresholdNumber(rule, "poorAbove");
  if (poorAbove !== null && numericValue > poorAbove) {
    return "air-poor";
  }

  const fairAbove = thresholdNumber(rule, "fairAbove");
  if (fairAbove !== null && numericValue > fairAbove) {
    return "air-fair";
  }

  return "air-good";
}

function clearAirQualityClasses(cell) {
  if (cell) {
    cell.classList.remove(...AIR_QUALITY_CLASS_NAMES);
  }
}

function metricValueFromCell(cell) {
  const storedValue = cell.getAttribute("data-air-quality-value");
  if (storedValue !== null && storedValue !== "") {
    return storedValue;
  }
  return cell.textContent;
}

function applyAirQualityClassWithThresholds(cell, thresholds) {
  if (!cell) {
    return "";
  }
  clearAirQualityClasses(cell);
  const className = airQualityClassForValue(
    cell.getAttribute("data-air-quality-metric"),
    metricValueFromCell(cell),
    thresholds,
  );
  if (className) {
    cell.classList.add(className);
  }
  return className;
}

function loadAirQualityThresholds() {
  if (cachedAirQualityThresholds) {
    return Promise.resolve(cachedAirQualityThresholds);
  }
  if (pendingAirQualityThresholds) {
    return pendingAirQualityThresholds;
  }
  if (typeof fetch === "undefined") {
    return Promise.resolve({});
  }

  pendingAirQualityThresholds = fetch(AIR_QUALITY_THRESHOLDS_URL)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    })
    .then((thresholds) => {
      cachedAirQualityThresholds = thresholds || {};
      return cachedAirQualityThresholds;
    })
    .catch((error) => {
      console.warn("Unable to load air quality thresholds", error);
      cachedAirQualityThresholds = {};
      return cachedAirQualityThresholds;
    });

  return pendingAirQualityThresholds;
}

function applyAirQualityClass(cell) {
  if (!cell) {
    return Promise.resolve("");
  }
  if (cachedAirQualityThresholds) {
    return Promise.resolve(
      applyAirQualityClassWithThresholds(cell, cachedAirQualityThresholds),
    );
  }
  return loadAirQualityThresholds().then((thresholds) =>
    applyAirQualityClassWithThresholds(cell, thresholds),
  );
}

function applyAirQualityClasses(root = document) {
  const cells = Array.from(root.querySelectorAll("[data-air-quality-metric]"));
  if (cells.length === 0) {
    return Promise.resolve();
  }
  return loadAirQualityThresholds().then((thresholds) => {
    cells.forEach((cell) => {
      applyAirQualityClassWithThresholds(cell, thresholds);
    });
  });
}

if (typeof window !== "undefined") {
  window.AirQualityThresholds = {
    airQualityClassForValue,
    applyAirQualityClass,
    applyAirQualityClasses,
    clearAirQualityClasses,
    loadAirQualityThresholds,
  };

  if (typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", function () {
      applyAirQualityClasses(document);
    });
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    airQualityClassForValue,
    airQualityNumber,
    applyAirQualityClassWithThresholds,
    clearAirQualityClasses,
  };
}
