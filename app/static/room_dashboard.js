// Room dashboard interactivity
const DEBUG = false;
const REFRESH_INTERVAL = 10; // seconds between refreshes
const FAN_SPEED_AUTO = -1; // Auto speed value

/**
 * Make API call to control device.
 * @param {string} endpoint - API endpoint
 * @param {Object} body - Request body
 * @param {string} errorMessage - Error message to show on failure
 * @returns {Promise<Object>} API response
 */
async function apiCall(endpoint, body, errorMessage) {
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json();
        if (DEBUG) {
            console.log(`${endpoint} result:`, result);
        }
        return result;
    } catch (e) {
        console.error(`Failed ${endpoint}:`, e);
        alert(errorMessage);
        throw e;
    }
}

/**
 * Set the fan drive (on/off).
 * @param {number} device_id - Device ID
 * @param {number} drive - 0 for off, 1 for on
 */
async function setDrive(device_id, drive) {
    return apiCall(
        '/api/v1/set_drive',
        { device_id, drive },
        'Error setting drive.'
    );
}

/**
 * Set the fan speed.
 * @param {number} device_id - Device ID
 * @param {number} fan_speed - Speed level (0-4)
 */
async function setFanSpeed(device_id, fan_speed) {
    if (DEBUG) {
        console.log("Setting device", device_id, "to speed", fan_speed);
    }
    return apiCall(
        '/api/v1/set_fan_speed',
        { device_id, fan_speed },
        'Error setting fan speed.'
    );
}

/**
 * Get status element for a device (works for both ERV and fan).
 * @param {number} deviceId - Device ID
 * @returns {HTMLElement|null} Status element or null
 */
function getDeviceStatusElement(deviceId) {
    return document.getElementById(`erv-${deviceId}-status`) ||
           document.getElementById(`fan-${deviceId}-status`);
}

/**
 * Get temperature element for a device (works for both ERV and fan).
 * @param {number} deviceId - Device ID
 * @returns {HTMLElement|null} Temperature element or null
 */
function getDeviceTempElement(deviceId) {
    return document.getElementById(`erv-${deviceId}-temp`) ||
           document.getElementById(`fan-${deviceId}-temp`);
}

/**
 * Show/hide loading state for a device.
 * @param {number} deviceId - Device ID
 * @param {boolean} isLoading - Whether to show loading state
 * @param {HTMLElement|null} activeButton - Button to show spinner on (if loading)
 */
function setDeviceLoading(deviceId, isLoading, activeButton = null) {
    const buttons = document.querySelectorAll(`button.speed-btn[data-device-id="${deviceId}"]`);
    const toggles = document.querySelectorAll(`input.drive-toggle[data-device-id="${deviceId}"]`);
    const statusEl = getDeviceStatusElement(deviceId);

    buttons.forEach(button => {
        if (isLoading) {
            if (activeButton && button === activeButton) {
                button.classList.add('loading');
            }
            button.disabled = true;
        } else {
            button.classList.remove('loading');
            button.disabled = false;
        }
    });

    toggles.forEach(toggle => {
        toggle.disabled = isLoading;
    });

    if (statusEl) {
        if (isLoading) {
            statusEl.textContent = 'Setting...';
            statusEl.classList.add('status-setting');
        } else {
            statusEl.classList.remove('status-setting');
        }
    }
}

/**
 * Handle drive toggle switch change.
 * @param {HTMLElement} toggle - Toggle checkbox element
 */
function handleDriveToggle(toggle) {
    const deviceId = parseInt(toggle.getAttribute('data-device-id'));
    const drive = toggle.checked ? 1 : 0;

    setDeviceLoading(deviceId, true);
    setDrive(deviceId, drive)
        .then(() => refreshStatus())
        .catch(() => setDeviceLoading(deviceId, false));
}

/**
 * Handle speed control button click.
 * @param {HTMLElement} button - Clicked button element
 */
function handleSpeedButton(button) {
    const deviceId = parseInt(button.getAttribute('data-device-id'));
    const speed = parseInt(button.getAttribute('data-speed'));

    setDeviceLoading(deviceId, true, button);

    const handleError = () => setDeviceLoading(deviceId, false);
    const handleSuccess = () => refreshStatus();

    // Set speed (and turn on motor if it's off)
    Promise.all([
        setDrive(deviceId, 1),
        setFanSpeed(deviceId, speed)
    ])
        .then(handleSuccess)
        .catch(handleError);
}

/**
 * Format temperature using TemperatureUtils if available.
 * @param {number} tempC - Temperature in Celsius
 * @returns {string} Formatted temperature string
 */
function formatTemperature(tempC) {
    if (window.TemperatureUtils) {
        return window.TemperatureUtils.formatTemperature(tempC);
    }
    return `${tempC.toFixed(1)}°C`;
}

/**
 * Update drive toggle state based on device status.
 * @param {number} deviceId - Device ID
 * @param {Object} device - Device data
 */
function updateDriveToggle(deviceId, device) {
    const toggle = document.querySelector(`input.drive-toggle[data-device-id="${deviceId}"]`);
    const isOn = device.drive === 'On' || device.drive === 1;

    if (toggle) {
        toggle.checked = isOn;
    }
}

/**
 * Update button active state based on device status.
 * Speed buttons are active when drive is on AND that speed is set.
 * Auto button is active when speed is -1 (regardless of drive state, as Auto can be set when off).
 * @param {HTMLElement} button - Button element
 * @param {Object} device - Device data
 */
function updateButtonActiveState(button, device) {
    button.classList.remove('active');
    const buttonSpeed = parseInt(button.getAttribute('data-speed'));
    const isOff = device.drive === 'Off' || device.drive === 0;
    const currentSpeed = parseInt(device.fan_speed || device.speed || 0);

    // Auto button: active when speed is -1 (can be set even when motor is off)
    if (buttonSpeed === FAN_SPEED_AUTO && currentSpeed === FAN_SPEED_AUTO) {
        button.classList.add('active');
    }
    // Speed button: active when drive is on AND this speed is set
    else if (!isOff && buttonSpeed === currentSpeed) {
        button.classList.add('active');
    }
}

/**
 * Update device status display from API data.
 * @param {Array<Object>} devices - Array of device data from API
 */
function updateDeviceStatus(devices) {
    devices.forEach(device => {
        const deviceId = device.device_id;
        const statusEl = getDeviceStatusElement(deviceId);
        const tempEl = getDeviceTempElement(deviceId);

        setDeviceLoading(deviceId, false);

        // Update status text (drive and speed are orthogonal)
        if (statusEl) {
            const isOff = device.drive === 'Off' || device.drive === 0;
            const speed = device.fan_speed || device.speed;
            const isAuto = speed === FAN_SPEED_AUTO;

            if (isOff) {
                statusEl.textContent = isAuto ? 'OFF (Auto)' :
                                      (speed != null ? `OFF (Speed ${speed})` : 'OFF');
            } else {
                statusEl.textContent = isAuto ? 'Auto' :
                                      (speed != null ? `Speed ${speed}` : 'ON');
            }
        }

        // Update temperature
        if (tempEl && device.temp10x != null) {
            const tempC = device.temp10x / 10;
            tempEl.setAttribute('data-temp-c', tempC);
            tempEl.textContent = formatTemperature(tempC);
        }

        // Update drive toggle state
        updateDriveToggle(deviceId, device);

        // Update button active states
        const buttons = document.querySelectorAll(`button.speed-btn[data-device-id="${deviceId}"]`);
        buttons.forEach(button => updateButtonActiveState(button, device));
    });
}

/**
 * Update Hubitat sensor temperature displays with current unit preference.
 */
function updateSensorTemperatures() {
    document.querySelectorAll('.sensor-temp[data-temp-c]').forEach(el => {
        const tempC = parseFloat(el.getAttribute('data-temp-c'));
        if (!isNaN(tempC)) {
            el.textContent = formatTemperature(tempC);
        }
    });
}

/**
 * Refresh device status from API.
 */
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

/**
 * Initialize sensor temperatures from template data.
 */
function initializeSensorTemperatures() {
    document.querySelectorAll('.sensor-temp[data-temp-c]').forEach(el => {
        const tempC = parseFloat(el.getAttribute('data-temp-c'));
        if (!isNaN(tempC)) {
            el.textContent = formatTemperature(tempC);
        }
    });
}

/**
 * Set up temperature unit toggle listener.
 */
function setupTemperatureToggle() {
    if (!window.TemperatureUtils) {
        return;
    }

    // Wait for temperature utils to initialize
    setTimeout(() => {
        const toggle = document.getElementById('temp-unit-toggle');
        if (!toggle) {
            return;
        }

        updateSensorTemperatures();

        toggle.addEventListener('change', () => {
            refreshStatus();
            updateSensorTemperatures();
        });
    }, 100);
}

/**
 * Initialize room dashboard functionality.
 */
function setupRoomDashboard() {
    // Set up drive toggle switches
    document.querySelectorAll('input.drive-toggle').forEach(toggle => {
        toggle.addEventListener('change', () => handleDriveToggle(toggle));
    });

    // Set up speed control buttons
    document.querySelectorAll('button.speed-btn[data-device-id][data-speed]').forEach(button => {
        button.addEventListener('click', () => handleSpeedButton(button));
    });

    initializeSensorTemperatures();
    setupTemperatureToggle();

    // Initial status refresh
    refreshStatus();

    // Set up periodic refresh
    setInterval(refreshStatus, REFRESH_INTERVAL * 1000);
}

window.addEventListener('DOMContentLoaded', setupRoomDashboard);
