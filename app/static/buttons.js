// interactivity for unit speed grid
var DEBUG=true;

function setStatus(msg) {
    var s = document.getElementById('status-div')
    s.textContent = msg;
}

// Function called to set the fan drive
async function setDrive(device_id, drive) {
    try {
	const response = await fetch('/api/v1/set_drive', {
	    method: 'POST',
	    headers: { 'Content-Type': 'application/json' },
	    body: JSON.stringify({ device_id: device_id, drive: drive })
	});
	const result = await response.json();
	console.log("Set drive: result=",result)
    } catch (e) {
	console.error('Failed to set fan_speed:', e);
	alert('Error setting fan_speed.');
    }
}

// Function called to set the fan_speed
async function setFanSpeed(name, device_id, fan_speed) {
    try {
        console.log("sending",device_id,fan_speed);
        setStatus(`Setting ${name} to ${fan_speed}`);
	const response = await fetch('/api/v1/set_fan_speed', {
	    method: 'POST',
	    headers: { 'Content-Type': 'application/json' },
	    body: JSON.stringify({ device_id: device_id, fan_speed: fan_speed })
	});
	const result = await response.json();
	console.log("Set fan_speed: result=",result)
        setStatus(`${name} set to ${fan_speed}`);
    } catch (e) {
	console.error('Failed to set fan_speed:', e);
        setStatus(`Error setting ${name} to ${fan_speed}`);
    }
}

// Refresh the rows in the fan control and temperature panel grid.
const setupButtons = () => {
    const lastSlashIndex = window.location.href.lastIndexOf('/');
    const base = window.location.href.substring(0, lastSlashIndex + 1);
    fetch(base + 'api/v1/status', { method: "GET"})
        .then(response => response.json())
        .then(data => {
            if (DEBUG) {
                console.log('Status data received:', data);
            }

	    for (const dev of data.devices) {
                if (dev.device_name=='ERV Kitchen'){
                    const k1 = document.getElementById('kitchen-1');
                    k1.addEventListener('click', function() {
                        setDrive(dev.device_id, 1);
                        setFanSpeed("ERV Kitchen", dev.device_id, 1);
                    });
                    const km = document.getElementById('kitchen-max');
                    km.addEventListener('click', function() {
                        setDrive(dev.device_id, 1);
                        setFanSpeed("ERV Kitchen", dev.device_id, 4);
                    });
                }
                if (dev.device_name=='ERV Restrooms'){
                    const rm = document.getElementById('restrooms-max');
                    rm.addEventListener('click', function() {
                        setDrive(dev.device_id, 1);
                        setFanSpeed("ERV Restrooms", dev.device_id, 4);
                    });
                    const r1 = document.getElementById('restrooms-1');
                    r1.addEventListener('click', function() {
                        setDrive(dev.device_id, 1);
                        setFanSpeed("ERV Restrooms", dev.device_id, 1);
                    });
                }
            }
        });
};

window.addEventListener('DOMContentLoaded', function() {
    setupButtons();
});
