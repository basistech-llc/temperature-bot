// interactivity for unit speed grid

console.log("unit_speed.js loaded");

// Constants
const REFRESH_INTERVAL = 10; // seconds between refreshes
const RUNNING_MINUTES = 10; // minutes to run before stopping
const DEBUG=false;
const SHOW_REFRESH_COUNTDOWN = false;
let lastRefreshTime = 0;

// Refresh logic
var start = Date.now();
var forceRefresh = false;
const FAN_SPEEDS = [-1, 0, 1, 2, 3, 4];

////////////////////////////////////////////////////////////////
// Weather display functions
function displayWeather(weatherInfo) {
    console.log('displayWeather called with:', weatherInfo);
    const weatherDiv = document.getElementById('weather');
    if (!weatherDiv || !weatherInfo) {
        console.log('Early return - weatherDiv:', !!weatherDiv, 'weatherInfo:', !!weatherInfo);
        return;
    }

    let html = '';
    // Add weather content
    if (weatherInfo.current) {
        const current = weatherInfo.current;
        const temp = current.temperature ? `${Math.round(current.temperature)}°C (Boston Logan Airport)` : 'N/A';
        html += `<div><strong>Current:</strong> ${temp} `;
        if (current.icon) {
            html += ` <img src="${current.icon}" alt="weather icon" class="weather-icon">`;
        }
        html += `${current.conditions}</div>`;
        console.log('Added current weather to HTML');
    }

    // Forecast
    if (weatherInfo.forecast && weatherInfo.forecast.length > 0) {
        html += `<div><strong>Forecast for CALA:</strong></div>`;
        weatherInfo.forecast.forEach(period => {
            html += `<div>${period.time} ${period.temperature}°F `;
            if (period.icon) {
                html += ` <img src="${period.icon}" alt="weather icon" class="weather-icon">`;
            }
            html += `${period.conditions}</div>`;
        });
        console.log('Added forecast to HTML');
    }
    weatherDiv.innerHTML = html;
}

////////////////////////////////////////////////////////////////
// Log tables
function getTodayUnixRange() {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const end = new Date(start.getTime() + 86400000); // midnight next day
    return {
        start: Math.floor(start.getTime() / 1000),
        end: Math.floor(end.getTime() / 1000)
    };
}

let logTable;
function createLogTable() {
    const { start, end } = getTodayUnixRange();
    console.log("start=",start,"end=",end);

    logTable = new Tabulator("#log-table", {
        layout: "fitColumns",
        height: "400px",
        ajaxURL: `/api/v1/logs?start=${start}&end=${end}`,
        ajaxResponse: function(url, params, response) {
            return response.data;  // Tabulator expects an array of row objects
        },
        columns: [
            {
                title: "Time", field: "logtime", sorter: "number",
                formatter: function(cell) {
                    const ts = cell.getValue() * 1000;
                    return new Date(ts).toLocaleString();
                },
                widthGrow: 2
            },
            { title: "IP Address", field: "ipaddr", widthGrow: 2 },
            { title: "Unit", field: "unit", hozAlign: "center" },
            { title: "Speed", field: "new_value", hozAlign: "center" },
            { title: "Agent", field: "agent", widthGrow: 2 },
            { title: "Comment", field: "comment", widthGrow: 3 }
        ],
        placeholder: "No logs found for today.",
        pagination: "local",
        paginationSize: 10
    });
}

function refreshLogTable() {
    const { start, end } = getTodayUnixRange();
    logTable.setData(`/api/v1/logs?start=${start}&end=${end}`);
}


////////////////////////////////////////////////////////////////


// Function called to set the speed
async function setFanSpeed(device_id, speed) {
    try {
	const response = await fetch('/api/v1/set_speed', {
	    method: 'POST',
	    headers: { 'Content-Type': 'application/json' },
	    body: JSON.stringify({ device_id: device_id, speed: speed })
	});

	const result = await response.json();
	console.log("Set speed: result=",result)
	forceRefresh = true;
    } catch (e) {
	console.error('Failed to set speed:', e);
	alert('Error setting speed.');
    }
}

// Add event listeners for radio buttons
function setupRadioButtonListeners() {
    const radioButtons = document.querySelectorAll('input[type="radio"][data-device-id]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            const deviceId = parseInt(this.getAttribute('data-device-id'));
            const speed = parseInt(this.getAttribute('data-speed'));
            setFanSpeed(deviceId, speed);
        });
    });
}

const refreshGrid = () => {
    const now = Date.now();
    const secondsSinceRefresh = Math.floor((now - lastRefreshTime) / 1000);
    const secondsUntilRefresh = forceRefresh ? 0 : (REFRESH_INTERVAL - secondsSinceRefresh);

    // Check if total runtime exceeded
    if ((now - start) > RUNNING_MINUTES * 60 * 1000) {
        document.querySelector('#status').innerHTML = 'stopped.';
        document.querySelector('#main-grid').innerHTML = 'Please click <b>reload</b> to restart the grid.';
        return;
    }

    // Update countdown display
    if (SHOW_REFRESH_COUNTDOWN) {
        document.querySelector('#next-update').innerHTML =
            secondsUntilRefresh <= 0 ? 'Refreshing...' : `Next refresh in ${secondsUntilRefresh} seconds`;
    }

    // If it's time to refresh
    if (secondsUntilRefresh <= 0) {
        refreshLogTable();
        const formData = new FormData();
        fetch(window.location.href + 'api/v1/status', { method: "GET"})
            .then(response => response.json())
            .then(data => {
                console.log('Status data received:', data);

                // Update the tables with the new data
		for (const dev of data.devices) {
		    console.log("dev=",dev);
		    if (dev.temp10x) {
			const cell = document.getElementById(`temp-${dev.device_id}`);
			var myformat = Intl.NumberFormat('en-US', {minimumIntegerDigits:2,
								   minimumFractionDigits:1});
			cell.innerHTML = myformat.format(dev.temp10x/10) + (dev.age ? ` <span class='age'>(${dev.age})</span> ` : '');

		    }
		    if (dev.speed) {
			const radio = document.getElementById(`radio-${dev.device_id}-${dev.drive_speed_val}`);
			if (radio) {
			    radio.checked = true;
			} else {
			    console.warn(`Radio button not found for radio-${dev.device_id}-${dev.drive_speed_val} dev=`,dev);
			}
		    }
		}

		// Update last refresh time
                var currentdate = new Date();
                const zeroPad = (num, places) => String(num).padStart(places, '0');
                var datetime = "Last Refresh: " +
                    currentdate.getFullYear() + "-" +
                    zeroPad(currentdate.getMonth() + 1, 2) + "-" +
                    zeroPad(currentdate.getDate(), 2) + " " +
                    zeroPad(currentdate.getHours(), 2) + ":" +
                    zeroPad(currentdate.getMinutes(), 2) + ":" +
                    zeroPad(currentdate.getSeconds(), 2);
                document.querySelector('#last-refresh').innerHTML = datetime;

                // Update the refresh time
                lastRefreshTime = now;
		forceRefresh = false;
            })
            .catch(error => {
                console.error('Error refreshing leaderboard:', error);
                // Still update the refresh time on error to prevent rapid retries
                lastRefreshTime = now;
            });
    }
    setTimeout(refreshGrid, 1000);    // Schedule next check in 1 second
};

/* This loads weather and starts the refresh cycle. */
async function loadWeatherAndStartRefresh() {
    console.log("Running loadWeatherAndStartRefresh()");
    try {
        fetch('api/v1/weather', { method: "GET"})
            .then(response => response.json())
            .then(data => {
                console.log('Weather data received:', data);

                const aqiValueElement = document.getElementById('aqi-value');
                const aqiNameElement =  document.getElementById('aqi-name');

                if (aqiValueElement && aqiNameElement ) {
		    if (data.aqi.error) {
			aqiValueElement.textContent = 'Error';
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
        refreshGrid();
    } catch (e) {
	console.error("Error in loadWeatherAndStartRefresh():", e);
    }
}


createLogTable();
window.addEventListener('DOMContentLoaded', function() {
    setupRadioButtonListeners();
    loadWeatherAndStartRefresh();
});
