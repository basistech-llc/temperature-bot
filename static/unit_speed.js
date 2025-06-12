// interactivity for unit speed grid

console.log("unit_speed.js loaded");

// Refresh logic

// Constants
const REFRESH_INTERVAL = 10; // seconds between refreshes
const RUNNING_MINUTES = 10; // minutes to run before stopping
let lastRefreshTime = 0;
var start = Date.now();
var forceRefresh = false;

const refreshGrid = () => {
    const now = Date.now();
    const secondsSinceRefresh = Math.floor((now - lastRefreshTime) / 1000);
    const secondsUntilRefresh = forceRefresh ? 0 : (REFRESH_INTERVAL - secondsSinceRefresh);
    
    // Check if total runtime exceeded
    if ((now - start) > RUNNING_MINUTES * 60 * 1000) {
        document.querySelector('#status').innerHTML = 'stopped.';
        document.querySelector('#grid').innerHTML = 'Please click <b>reload</b> to restart the grid.';
        return;
    }

    // Update countdown display
    document.querySelector('#next-update').innerHTML =
        secondsUntilRefresh <= 0 ? 'Refreshing...' : `Next refresh in ${secondsUntilRefresh} seconds`;
    
    // If it's time to refresh
    if (secondsUntilRefresh <= 0) {
        const formData = new FormData();
        fetch(window.location.href + 'api/v1/status', { method: "GET"})
            .then(response => response.json())
            .then(data => {
                document.getElementById('aqi-value').textContent = data.AQI.value;
                document.getElementById('aqi-name').textContent = data.AQI.name;
                document.getElementById('aqi-name').style.backgroundColor = data.AQI.color;
		
                // Update the tables with the new data
		for (const [unit, d] of Object.entries(data.ERV)) {
		    console.log("unit=",unit,"d=",d);
		    document.getElementById(`unit-${unit}-status`).textContent = `speed: ${d.val}`;
		}

		// Update the countdown
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
    
    // Schedule next check in 1 second
    setTimeout(refreshGrid, 1000);
};	    


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


async function loadMapAndRenderGrid() {
    console.log("Running loadMapAndRenderGrid()");
    try {
	const res = await fetch('/api/v1/system_map');
	const systemMap = await res.json();
	console.log("Got system map:", systemMap);

	const speeds = [0, 1, 2, 3, 4];
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
		const button = document.createElement('button');
		button.textContent = speed;
		button.className = 'pure-button';
		button.onclick = () => setSpeed(unit, speed);
		cell.appendChild(button);
		row.appendChild(cell);
	    });

	    table.appendChild(row);
	}
	document.getElementById('grid').appendChild(table);
	refreshGrid();		// and schedule a refresh
    } catch (e) {
	console.error("Error in loadMapAndRenderGrid():", e);
    }
}
window.addEventListener('DOMContentLoaded', loadMapAndRenderGrid);

