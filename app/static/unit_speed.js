// interactivity for unit speed grid

console.log("unit_speed.js loaded");

// Constants
const DEBUG = false;
const REFRESH_INTERVAL = 10; // seconds between refreshes
const RUNNING_MINUTES = 10; // minutes to run before stopping
const SHOW_REFRESH_COUNTDOWN = false;
let lastRefreshTime = 0;

const LOG_DAYS = 5;
const SECONDS_PER_DAY = 60 * 60 * 24;

// Refresh logic
var start = Date.now();
var forceRefresh = false;
const FAN_SPEEDS = [-1, 0, 1, 2, 3, 4];

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
}

////////////////////////////////////////////////////////////////
// Log tables
function getTodayUnixRange() {
  const now = new Date();
  const start_today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );
  const start = new Date(
    start_today.getTime() - (LOG_DAYS - 1) * SECONDS_PER_DAY * 1000,
  );
  const end = new Date(start_today.getTime() + 86400000); // midnight next day
  return {
    start: Math.floor(start.getTime() / 1000),
    end: Math.floor(end.getTime() / 1000),
  };
}

let logTable;
function createLogTable() {
  const { start, end } = getTodayUnixRange();
  console.log("start=", start, "end=", end);

  logTable = new Tabulator("#log-table", {
    layout: "fitColumns",
    height: "400px",
    ajaxURL: `/api/v1/logs?start=${start}&end=${end}`,
    ajaxResponse: function (url, params, response) {
      return response.data; // Tabulator expects an array of row objects
    },
    columns: [
      {
        title: "Time",
        field: "logtime",
        sorter: "number",
        formatter: function (cell) {
          const ts = cell.getValue() * 1000;
          return new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZoneName: "short",
          }).format(new Date(ts));
        },
        widthGrow: 2,
      },
      { title: "IP Address", field: "ipaddr", widthGrow: 2 },
      { title: "Unit", field: "unit", hozAlign: "center" },
      { title: "Speed", field: "new_value", hozAlign: "center" },
      { title: "Agent", field: "agent", widthGrow: 2 },
      { title: "Comment", field: "comment", widthGrow: 3 },
    ],
    placeholder: "No logs found for today.",
    pagination: "local",
    paginationSize: 10,
  });
}

function refreshLogTable() {
  const { start, end } = getTodayUnixRange();
  logTable.setData(`/api/v1/logs?start=${start}&end=${end}`);
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

// Handle all user events
function setupMatrixListenerss() {
  // Add event listeners for fan sliders
  const driveSwitches = document.querySelectorAll(
    'input[type="checkbox"][x-drive]',
  );
  driveSwitches.forEach((ds) => {
    ds.addEventListener("change", function () {
      const deviceId = parseInt(this.getAttribute("x-data-device-id"));
      setDrive(deviceId, this.checked ? 1 : 0);
    });
  });
  // Add event listeners for radio buttons
  const radioButtons = document.querySelectorAll(
    'input[type="radio"][x-data-device-id]',
  );
  radioButtons.forEach((radio) => {
    radio.addEventListener("change", function () {
      const deviceId = parseInt(this.getAttribute("x-data-device-id"));
      const fan_speed = parseInt(this.getAttribute("x-data-fan_speed"));
      setFanSpeed(deviceId, fan_speed);
    });
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
    refreshLogTable();
    const formData = new FormData();
    fetch(window.location.href + "api/v1/status", { method: "GET" })
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
              var myformat = Intl.NumberFormat("en-US", {
                minimumIntegerDigits: 2,
                minimumFractionDigits: 1,
              });
              cell.innerHTML =
                TemperatureUtils.formatTemperature(dev.temp10x / 10) +
                (dev.age ? ` <span class='age'>(${dev.age})</span> ` : "");
            }
            if (dev.drive) {
              const slider = document.getElementById(
                `fan_drive-${dev.device_id}`,
              );
              if (slider) {
                slider.checked = dev.drive ? true : false;
              } else {
                console.warn(
                  `Drive slider not found for fan_drive${dev.device_ide} dev=`,
                  dev,
                );
              }
            }
            if (dev.fan_speed) {
              const radio = document.getElementById(
                `radio-${dev.device_id}-${dev.fan_speed}`,
              );
              if (radio) {
                radio.checked = true;
              } else {
                console.warn(
                  `Radio button not found for radio-${dev.device_id}-${dev.fan_speed} dev=`,
                  dev,
                );
              }
            }
            if (dev.notes) {
              const cell = document.getElementById(`notes-${dev.device_id}`);
              cell.innerHTML = dev.notes;
            }
            if (dev.disabled_until) {
              dt = new Date(dev.disabled_until * 1000);
              const cell = document.getElementById(
                `notes-disabled-${dev.device_id}`,
              );
              cell.innerHTML = `Rules disabled until ${asctime(dt)}`;
            }
          }

        // Update last refresh time
        const lr = document.getElementById("last-refresh");
        lr.innerHtml = "Last Refresh: " + asctime(new Date());

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

// Make refreshGridRows available globally for temperature unit changes
window.refreshGridRows = refreshGridRows;

createLogTable();
window.addEventListener("DOMContentLoaded", function () {
  setupMatrixListenerss();
  loadWeatherAndStartRefresh();
});
