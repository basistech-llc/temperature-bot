// Room dashboard interactivity
const DEBUG = false;
const REFRESH_INTERVAL = 10; // seconds between refreshes

// Function to set the fan drive
async function setDrive(device_id, drive) {
    try {
        const response = await fetch('/api/v1/set_drive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: device_id, drive: drive })
        });
        const result = await response.json();
        console.log("Set drive: result=", result);
        return result;
    } catch (e) {
        console.error('Failed to set drive:', e);
        alert('Error setting drive.');
        throw e;
    }
}

// Function to set the fan speed
async function setFanSpeed(device_id, fan_speed) {
    try {
        console.log("Setting device", device_id, "to speed", fan_speed);
        const response = await fetch('/api/v1/set_fan_speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: device_id, fan_speed: fan_speed })
        });
        const result = await response.json();
        console.log("Set fan_speed: result=", result);
        return result;
    } catch (e) {
        console.error('Failed to set fan_speed:', e);
        alert('Error setting fan speed.');
        throw e;
    }
}

// Show loading state for a device
function setDeviceLoading(deviceId, isLoading, activeButton = null) {
    const buttons = document.querySelectorAll(`button[data-device-id="${deviceId}"]`);
    const statusEl = document.getElementById(`erv-${deviceId}-status`) ||
                    document.getElementById(`fan-${deviceId}-status`);

    buttons.forEach(button => {
        if (isLoading) {
            // Only show spinner on the active button
            if (activeButton && button === activeButton) {
                button.classList.add('loading');
            }
            // But disable all buttons
            button.disabled = true;
        } else {
            // Clear loading state from all buttons
            button.classList.remove('loading');
            button.disabled = false;
        }
    });

    if (statusEl && isLoading) {
        statusEl.textContent = 'Setting...';
        statusEl.classList.add('status-setting');
    } else if (statusEl) {
        statusEl.classList.remove('status-setting');
    }
}

// Handle button clicks for speed control
function handleSpeedButton(button) {
    const deviceId = parseInt(button.getAttribute('data-device-id'));
    const speed = parseInt(button.getAttribute('data-speed'));

    // Show loading state immediately (spinner only on clicked button)
    setDeviceLoading(deviceId, true, button);

    if (speed === 0) {
        // Turn off (set drive to 0)
        setDrive(deviceId, 0)
            .then(() => {
                // Refresh status will clear loading state
                refreshStatus();
            })
            .catch(() => {
                // Clear loading state on error
                setDeviceLoading(deviceId, false);
            });
    } else {
        // Turn on and set speed
        Promise.all([
            setDrive(deviceId, 1),
            setFanSpeed(deviceId, speed)
        ])
            .then(() => {
                // Refresh status will clear loading state
                refreshStatus();
            })
            .catch(() => {
                // Clear loading state on error
                setDeviceLoading(deviceId, false);
            });
    }
}

// Update device status display
function updateDeviceStatus(devices) {
    devices.forEach(device => {
        const deviceId = device.device_id;
        const statusEl = document.getElementById(`erv-${deviceId}-status`) ||
                        document.getElementById(`fan-${deviceId}-status`);
        const tempEl = document.getElementById(`erv-${deviceId}-temp`) ||
                       document.getElementById(`fan-${deviceId}-temp`);

        // Clear loading state when status updates
        setDeviceLoading(deviceId, false);

        // Update status text
        if (statusEl) {
            if (device.drive === 'Off' || device.drive === 0) {
                statusEl.textContent = 'OFF';
            } else {
                const speed = device.fan_speed || device.speed || '--';
                statusEl.textContent = `Speed ${speed}`;
            }
        }

        // Update temperature
        if (tempEl && device.temp10x !== null && device.temp10x !== undefined) {
            const tempC = device.temp10x / 10;
            tempEl.setAttribute('data-temp-c', tempC);
            if (window.TemperatureUtils) {
                tempEl.textContent = window.TemperatureUtils.formatTemperature(tempC);
            } else {
                tempEl.textContent = `${tempC.toFixed(1)}°C`;
            }
        }

        // Update button active states
        const buttons = document.querySelectorAll(`button[data-device-id="${deviceId}"]`);
        buttons.forEach(button => {
            button.classList.remove('active');
            const buttonSpeed = parseInt(button.getAttribute('data-speed'));

            if (device.drive === 'Off' || device.drive === 0) {
                if (buttonSpeed === 0) {
                    button.classList.add('active');
                }
            } else {
                const currentSpeed = parseInt(device.fan_speed || device.speed || 0);
                if (buttonSpeed === currentSpeed) {
                    button.classList.add('active');
                }
            }
        });
    });
}

// Update Hubitat sensor temperatures
function updateSensorTemperatures() {
    // Update all sensor temperature displays with current unit preference
    document.querySelectorAll('.sensor-temp[data-temp-c]').forEach(el => {
        const tempC = parseFloat(el.getAttribute('data-temp-c'));
        if (!isNaN(tempC) && window.TemperatureUtils) {
            el.textContent = window.TemperatureUtils.formatTemperature(tempC);
        }
    });
}

// Refresh device status from API
function refreshStatus() {
    fetch('/api/v1/status')
        .then(response => response.json())
        .then(data => {
            if (DEBUG) {
                console.log('Status data received:', data);
            }
            updateDeviceStatus(data.devices);
        })
        .catch(error => {
            console.error('Failed to refresh status:', error);
        });
}

// Setup button event listeners
function setupRoomDashboard() {
    // Set up speed control buttons
    document.querySelectorAll('button[data-device-id][data-speed]').forEach(button => {
        button.addEventListener('click', function() {
            handleSpeedButton(this);
        });
    });

    // Initialize sensor temperatures from template data
    document.querySelectorAll('.sensor-temp[data-temp-c]').forEach(el => {
        const tempC = parseFloat(el.getAttribute('data-temp-c'));
        if (!isNaN(tempC) && window.TemperatureUtils) {
            el.textContent = window.TemperatureUtils.formatTemperature(tempC);
        }
    });

    // Set up temperature unit toggle listener
    if (window.TemperatureUtils) {
        // Wait for temperature utils to initialize
        setTimeout(() => {
            const toggle = document.getElementById('temp-unit-toggle');
            if (toggle) {
                // Update initial display
                updateSensorTemperatures();

                toggle.addEventListener('change', function() {
                    // Update all temperature displays when toggle changes
                    // Re-fetch and update device status
                    refreshStatus();
                    updateSensorTemperatures();
                });
            }
        }, 100);
    }

    // Initial status refresh
    refreshStatus();

    // Set up periodic refresh
    setInterval(refreshStatus, REFRESH_INTERVAL * 1000);
}

window.addEventListener('DOMContentLoaded', setupRoomDashboard);
