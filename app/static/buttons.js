// interactivity for unit speed grid

var DEBUG=true;

console.log("buttons.js loaded");

// Function called to set the fan drive
async function setDrive(device_id, drive) {
    console.log(`setDrive(${device_id},${drive})`);
    try {
	const response = await fetch('/api/v1/set_drive', {
	    method: 'POST',
	    headers: { 'Content-Type': 'application/json' },
	    body: JSON.stringify({ device_id: device_id, drive: drive })
	});
	const result = await response.json();
	console.log("Set drive: result=",result)
	forceRefresh = true;
    } catch (e) {
	console.error('Failed to set fan_speed:', e);
	alert('Error setting fan_speed.');
    }
}

// Function called to set the fan_speed
async function setFanSpeed(device_id, fan_speed) {
    console.log(`setFanSpeed(${device_id},${fan_speed})`);
    try {
        console.log("sending",device_id,fan_speed);
	const response = await fetch('/api/v1/set_fan_speed', {
	    method: 'POST',
	    headers: { 'Content-Type': 'application/json' },
	    body: JSON.stringify({ device_id: device_id, fan_speed: fan_speed })
	});
	const result = await response.json();
	console.log("Set fan_speed: result=",result)
	forceRefresh = true;
    } catch (e) {
	console.error('Failed to set fan_speed:', e);
	alert('Error setting fan_speed.');
    }
}

// Handle all user events
function setupMatrixListenerss() {
    // Add event listeners for fan sliders
    const driveSwitches = document.querySelectorAll('input[type="checkbox"][x-drive]');
    driveSwitches.forEach(ds => {
        ds.addEventListener('change', function() {
            const deviceId = parseInt(this.getAttribute('x-data-device-id'));
            console.log("this=",this,"this.checked=",this.checked);
            setDrive(deviceId, this.checked ? 1 : 0);
        });
    });
    // Add event listeners for radio buttons
    const radioButtons = document.querySelectorAll('input[type="radio"][x-data-device-id]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            const deviceId = parseInt(this.getAttribute('x-data-device-id'));
            const fan_speed = parseInt(this.getAttribute('x-data-fan_speed'));
            setFanSpeed(deviceId, fan_speed);
        });
    });
}

// Refresh the rows in the fan control and temperature panel grid.
const setupButtons = () => {
    const lastSlashIndex = window.location.href.lastIndexOf('/');
    const base = window.location.href.substring(0, lastSlashIndex + 1);
    console.log("base=",base);

    fetch(base + 'api/v1/status', { method: "GET"})
        .then(response => response.json())
        .then(data => {
            if (DEBUG) {
                console.log('Status data received:', data);
            }

	    for (const dev of data.devices) {
                if (dev.device_name=='ERV Kitchen'){
                    const km = document.getElementById('kitchen-max');
                    km.addEventListener('click', function() {
                        console.log('clicked. dev=',dev);
                        setDrive(dev.device_id, 1);
                        setFanSpeed(dev.device_id, 4);
                    });
                    const k1 = document.getElementById('kitchen-1');
                    k1.addEventListener('click', function() {
                        console.log('clicked. dev=',dev);
                        setDrive(dev.device_id, 1);
                        setFanSpeed(dev.device_id, 1);
                    });
                }
                if (dev.device_name=='ERV Restrooms'){
                    const rm = document.getElementById('restrooms-max');
                    rm.addEventListener('click', function() {
                        console.log('clicked. dev=',dev);
                        setDrive(dev.device_id, 1);
                        setFanSpeed(dev.device_id, 4);
                    });
                    const r1 = document.getElementById('restrooms-1');
                    r1.addEventListener('click', function() {
                        console.log('clicked. dev=',dev);
                        setDrive(dev.device_id, 1);
                        setFanSpeed(dev.device_id, 1);
                    });
                }
            }
        });
};

window.addEventListener('DOMContentLoaded', function() {
    setupButtons();
});
