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

////////////////////////////////////////////////////////////////
// Weather display functions
function displayWeather(weatherInfo) {
    console.log('displayWeather called with:', weatherInfo);
    const weatherDiv = document.getElementById('weather');
    console.log('weatherDiv found:', !!weatherDiv);
    if (!weatherDiv || !weatherInfo) {
        console.log('Early return - weatherDiv:', !!weatherDiv, 'weatherInfo:', !!weatherInfo);
        return;
    }
    
    // Preserve existing AQI elements
    const aqiStatus = weatherDiv.querySelector('#aqi-status');
    const status = weatherDiv.querySelector('#status');
    const lastUpdate = weatherDiv.querySelector('#last-update');
    const nextUpdate = weatherDiv.querySelector('#next-update');
    
    console.log('Preserved elements:', {
        aqiStatus: !!aqiStatus,
        status: !!status,
        lastUpdate: !!lastUpdate,
        nextUpdate: !!nextUpdate
    });
    
    let html = '';
    
    // Add back the preserved elements
    if (aqiStatus) html += aqiStatus.outerHTML;
    if (status) html += status.outerHTML;
    if (lastUpdate) html += lastUpdate.outerHTML;
    if (nextUpdate) html += nextUpdate.outerHTML;
    
    // Add weather content
    if (weatherInfo.current) {
        const current = weatherInfo.current;
        const temp = current.temperature ? `${Math.round(current.temperature)}°F` : 'N/A';
        html += `<div><strong>Current:</strong> ${temp} ${current.conditions}`;
        if (current.icon) {
            html += ` <img src="${current.icon}" alt="weather icon" class="weather-icon">`;
        }
        html += `</div>`;
        console.log('Added current weather to HTML');
    }
    
    // Forecast
    if (weatherInfo.forecast && weatherInfo.forecast.length > 0) {
        html += `<div><strong>Forecast:</strong></div>`;
        weatherInfo.forecast.forEach(period => {
            html += `<div>${period.time} ${period.temperature}°F ${period.conditions}`;
            if (period.icon) {
                html += ` <img src="${period.icon}" alt="weather icon" class="weather-icon">`;
            }
            html += `</div>`;
        });
        console.log('Added forecast to HTML');
    }
    
    console.log('Final HTML length:', html.length);
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
async function setSpeed(unit, speed) {
    try {
	const response = await fetch('/api/v1/set_speed', {
	    method: 'POST',
	    headers: { 'Content-Type': 'application/json' },
	    body: JSON.stringify({ unit: unit, speed: speed })
	});

	const result = await response.json();
	console.log("Set speed: result=",result)
	forceRefresh = true;
    } catch (e) {
	console.error('Failed to set speed:', e);
	alert('Error setting speed.');
    }
}

// Updates the speed in the UI
function setRadioSpeed(unit, speed) {
    const radio = document.getElementById(`radio-${unit}-${speed}`);
    if (radio) {
        radio.checked = true;
    } else {
        console.warn(`Radio button for unit ${unit} speed ${speed} not found.`);
    }
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
                
                // Check if elements exist before trying to update
                const aqiValueElement = document.getElementById('aqi-value');
                const aqiNameElement = document.getElementById('aqi-name');
                
                console.log('Element check:', {
                    aqiValueElement: aqiValueElement,
                    aqiNameElement: aqiNameElement,
                    aqiData: data.aqi
                });
                
                if (aqiValueElement && aqiNameElement && data.aqi) {
                    aqiValueElement.textContent = data.aqi.value;
                    aqiNameElement.textContent = data.aqi.name;
                    aqiNameElement.style.backgroundColor = data.aqi.color;
                    console.log('AQI updated:', data.aqi);
                } else {
                    console.error('AQI elements not found or data missing:', {
                        aqiValueElement: !!aqiValueElement,
                        aqiNameElement: !!aqiNameElement,
                        aqiData: !!data.aqi
                    });
                }

                // Display weather information if available
                if (data.weather) {
                    console.log('Weather data found:', data.weather);
                    displayWeather(data.weather);
                } else {
                    console.log('No weather data in response');
                }

                // Update the tables with the new data
		for (const [unit, d] of Object.entries(data.devices)) {
		    console.log("unit=",unit,"d=",d);
		    // document.getElementById(`unit-${unit}-status`).textContent = `speed: ${d.val}`;
                    setRadioSpeed(unit, d.val);
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
                document.querySelector('#last-update').innerHTML = datetime;

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

async function loadMapAndRenderGrid() {
    console.log("Running loadMapAndRenderGrid()");
    try {
	const res = await fetch('/api/v1/system_map');
	const systemMap = await res.json();
	console.log("Got system map:", systemMap);

	const speeds = [-1, 0, 1, 2, 3, 4];
        const form = document.createElement('form');
        document.getElementById('main-grid').appendChild(form);

	const table = document.createElement('table');
	table.className = 'pure-table pure-table-bordered';

	// Header row
	const headerRow = document.createElement('tr');
	headerRow.innerHTML = `<th>Unit</th>` + speeds.map(s => `<th>${s}</th>`).join('');
	table.appendChild(headerRow);

	// Rows
	for (const [unit, label] of Object.entries(systemMap)) {
	    const row = document.createElement('tr');
	    const labelCell = document.createElement('td');
	    labelCell.innerHTML = label + ` <span id="unit-${unit}-status"></span>`;
	    row.appendChild(labelCell);

	    speeds.forEach(speed => {
		const cell = document.createElement('td');
                cell.classList.add('speed');
		const radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = `speed-${unit}`;
                radio.value = speed;
                radio.id = `radio-${unit}-${speed}`;
		radio.onclick = () => setSpeed(unit, speed);
		cell.appendChild(radio);
		row.appendChild(cell);
	    });

	    table.appendChild(row);
	}
	form.appendChild(table);
	refreshGrid();		// and schedule a refresh
    } catch (e) {
	console.error("Error in loadMapAndRenderGrid():", e);
    }
}


createLogTable();
window.addEventListener('DOMContentLoaded', loadMapAndRenderGrid);
