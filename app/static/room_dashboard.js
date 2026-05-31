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
 * Friendly label for a speed, read off this device's matching speed button.
 *
 * The buttons are the single source of truth for speed names: they're rendered
 * per device type (ERV vs fan), so reading from them yields the correct label
 * (e.g. the off-button "was …" history note) without duplicating the label map.
 *
 * @param {number} deviceId - Device ID
 * @param {number} speed - Speed value (matches a button's data-speed)
 * @returns {string} Button label (e.g. 'HI', 'MED-LO', 'Auto'), or a
 *                    'Speed N' fallback if no matching button exists
 */
function speedButtonLabel(deviceId, speed) {
    const btn = document.querySelector(
        `button.speed-btn[data-device-id="${deviceId}"][data-speed="${speed}"]`);
    return btn ? btn.textContent.trim() : `Speed ${speed}`;
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
 * Handle speed control button click.
 * @param {HTMLElement} button - Clicked button element
 */
function handleSpeedButton(button) {
    const deviceId = parseInt(button.getAttribute('data-device-id'));
    const speed = parseInt(button.getAttribute('data-speed'));

    setDeviceLoading(deviceId, true, button);

    const handleError = () => setDeviceLoading(deviceId, false);
    const handleSuccess = () => refreshStatus();

    // Off button: turn off motor
    if (speed === 0) {
        setDrive(deviceId, 0)
            .then(handleSuccess)
            .catch(handleError);
    }
    // Speed buttons: set speed (and turn on motor if it's off)
    else {
        Promise.all([
            setDrive(deviceId, 1),
            setFanSpeed(deviceId, speed)
        ])
            .then(handleSuccess)
            .catch(handleError);
    }
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
 * Update button active state based on device status.
 *
 * One-dimensional control: exactly one button is highlighted. When the unit is
 * off, only the Off button is active — the held speed (Auto included) is purely
 * historical (shown as the "was …" note), never a second highlighted button.
 * When on, the button matching the current speed is active; Auto is just the
 * speed value -1, so it needs no special case.
 * @param {HTMLElement} button - Button element
 * @param {Object} device - Device data
 */
function updateButtonActiveState(button, device) {
    button.classList.remove('active');
    const buttonSpeed = parseInt(button.getAttribute('data-speed'));
    const isOff = device.drive === 'Off' || device.drive === 0;
    const currentSpeed = parseInt(device.fan_speed || device.speed || 0);

    // Off button (speed 0): active only when the unit is off.
    if (buttonSpeed === 0) {
        if (isOff) {
            button.classList.add('active');
        }
    }
    // Speed/Auto buttons: active only when on AND matching the current speed.
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

        // The button row is the one-dimensional source of truth for the
        // current setting (whichever button glows), so the header carries no
        // speed text — that slot is reserved for the transient "Setting…" note.
        if (statusEl) {
            statusEl.textContent = '';
        }

        // When the unit is off, surface the speed it had been running at as a
        // small historical note on the (already-selected) Off button. In our
        // one-dimensional model the held hardware speed is NOT a resume target
        // — it's just history — so it never decorates a speed button.
        const offBtn = document.querySelector(
            `button.speed-btn.speed-off[data-device-id="${deviceId}"]`);
        if (offBtn) {
            const isOff = device.drive === 'Off' || device.drive === 0;
            const speed = device.fan_speed || device.speed;
            if (isOff && speed != null) {
                // ERVs expose no Auto button, so name Auto directly rather than
                // reading a label that would fall back to 'Speed -1'.
                const wasLabel = speed === FAN_SPEED_AUTO ? 'Auto' :
                                 speedButtonLabel(deviceId, speed);
                offBtn.innerHTML =
                    '<span class="off-label">Off</span>' +
                    `<span class="off-history">was ${wasLabel}</span>`;
            } else {
                offBtn.textContent = 'Off';
            }
        }

        // Update temperature
        if (tempEl && device.temp10x != null) {
            const tempC = device.temp10x / 10;
            tempEl.setAttribute('data-temp-c', tempC);
            tempEl.textContent = formatTemperature(tempC);
        }

        // Update set temperature from AE-200 status
        const setTempDisplay = document.getElementById(`settemp-display-${deviceId}`);
        if (setTempDisplay) {
            const status = device.status || {};
            const rawSetTemp = status.SetTemp;
            if (rawSetTemp !== undefined && rawSetTemp !== '' && rawSetTemp !== '0') {
                const setTempC = parseFloat(rawSetTemp);
                if (!isNaN(setTempC)) {
                    setTempDisplay.setAttribute('data-temp-c', setTempC.toString());
                    setTempDisplay.textContent = formatTemperature(setTempC);
                }
            }
        }

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
 * Debounce helper — calls fn at most once per delay ms.
 */
function debounce(fn, delay) {
    let timer = null;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

/**
 * Set the dimmer level via API.
 * @param {number} level - 0-100
 */
function setDimmerLevel(level) {
    apiCall(
        '/api/v1/hickory/dimmer',
        { level },
        'Error setting dimmer.'
    );
}

/**
 * Fetch room control status and update UI.
 */
function refreshRoomStatus() {
    fetch('/api/v1/hickory/room_status')
        .then(response => response.json())
        .then(data => {
            if (data.dimmer) {
                const slider = document.getElementById('dimmer-slider');
                const valueEl = document.getElementById('dimmer-value');
                if (slider && !slider.matches(':active')) {
                    slider.value = data.dimmer.level;
                }
                if (valueEl) {
                    valueEl.textContent = data.dimmer.level + '%';
                }
            }
            if (data.wall_inner) {
                updateWallButton('inner', data.wall_inner.switch);
            }
            if (data.wall_outer) {
                updateWallButton('outer', data.wall_outer.switch);
            }
        })
        .catch(error => {
            if (DEBUG) {
                console.error('Failed to refresh room status:', error);
            }
        });
}

/**
 * Set up dimmer slider interaction.
 */
function setupDimmer() {
    const slider = document.getElementById('dimmer-slider');
    if (!slider) {
        return;
    }

    const valueEl = document.getElementById('dimmer-value');
    const debouncedSet = debounce(setDimmerLevel, 300);

    slider.addEventListener('input', () => {
        const level = parseInt(slider.value);
        if (valueEl) {
            valueEl.textContent = level + '%';
        }
        debouncedSet(level);
    });
}

/**
 * Update a wall light button to reflect current state.
 * @param {string} light - 'inner' or 'outer'
 * @param {string} state - 'on' or 'off'
 */
function updateWallButton(light, state) {
    const btn = document.getElementById('wall-' + light + '-btn');
    if (!btn) {
        return;
    }
    const isOn = state === 'on';
    btn.textContent = isOn ? 'ON' : 'OFF';
    btn.classList.toggle('is-on', isOn);
}

/**
 * Handle wall light button click — toggle on/off.
 * @param {HTMLElement} button - Clicked button element
 */
function handleWallButton(button) {
    const light = button.getAttribute('data-light');
    const isOn = button.classList.contains('is-on');
    const newState = isOn ? 'off' : 'on';

    button.disabled = true;
    apiCall(
        '/api/v1/hickory/wall_light',
        { light, state: newState },
        'Error toggling wall light.'
    ).then(() => {
        updateWallButton(light, newState);
        button.disabled = false;
    }).catch(() => {
        button.disabled = false;
    });
}

/**
 * Handle TV control button click.
 * @param {HTMLElement} button - Clicked button element
 */
function handleTvButton(button) {
    const direction = button.getAttribute('data-direction');
    const buttons = document.querySelectorAll('.tv-btn');
    buttons.forEach(b => { b.disabled = true; });

    apiCall(
        '/api/v1/hickory/tv',
        { direction },
        'Error controlling TV.'
    ).then(() => {
        buttons.forEach(b => { b.disabled = false; });
    }).catch(() => {
        buttons.forEach(b => { b.disabled = false; });
    });
}

/**
 * Initialize set temperature controls using compact up/down buttons.
 * Buttons operate in the currently selected UI unit but send Celsius to backend.
 */
function setupSetTempControls() {
    document.querySelectorAll('.settemp-btn').forEach(button => {
        button.addEventListener('click', function() {
            const deviceId = parseInt(this.getAttribute('data-device-id'));
            const delta = parseFloat(this.getAttribute('data-delta') || '0');
            const display = document.getElementById(`settemp-display-${deviceId}`);
            if (!display) return;

            const currentCAttr = display.getAttribute('data-temp-c');
            let currentC = currentCAttr ? parseFloat(currentCAttr) : NaN;
            if (isNaN(currentC)) currentC = 21.0;

            const useFahrenheit = window.TemperatureUtils && window.TemperatureUtils.getTemperatureUnitPreference();
            let currentUI = currentC;
            if (useFahrenheit) currentUI = window.TemperatureUtils.celsiusToFahrenheit(currentC);

            let newUI = currentUI + delta;
            const minUI = useFahrenheit ? 50 : 10;
            const maxUI = useFahrenheit ? 86 : 30;
            newUI = Math.max(minUI, Math.min(maxUI, newUI));

            let newC = useFahrenheit ? window.TemperatureUtils.fahrenheitToCelsius(newUI) : newUI;
            newC = Math.round(newC * 10) / 10;

            display.setAttribute('data-temp-c', newC.toString());
            display.textContent = formatTemperature(newC);

            setDeviceSetTemp(deviceId, newC);
        });
    });
}

/**
 * Call backend API to set device set temperature in Celsius.
 * @param {number} deviceId
 * @param {number} setTempC
 */
async function setDeviceSetTemp(deviceId, setTempC) {
    try {
        await apiCall(
            '/api/v1/set_temp',
            { device_id: deviceId, set_temp_c: setTempC },
            'Error setting temperature.'
        );
        refreshStatus();
    } catch (e) {
        // Error already handled by apiCall
    }
}

/**
 * Initialize room dashboard functionality.
 */
function setupRoomDashboard() {
    // Set up speed control buttons
    document.querySelectorAll('button.speed-btn[data-device-id][data-speed]').forEach(button => {
        button.addEventListener('click', () => handleSpeedButton(button));
    });

    // Set up TV control buttons
    document.querySelectorAll('.tv-btn[data-direction]').forEach(button => {
        button.addEventListener('click', () => handleTvButton(button));
    });

    // Set up set temperature controls
    setupSetTempControls();

    // Set up dimmer
    setupDimmer();

    // Set up wall light buttons
    document.querySelectorAll('.wall-btn[data-light]').forEach(button => {
        button.addEventListener('click', () => handleWallButton(button));
    });

    initializeSensorTemperatures();
    setupTemperatureToggle();

    // Initial status refresh
    refreshStatus();
    refreshRoomStatus();

    // Set up periodic refresh
    setInterval(refreshStatus, REFRESH_INTERVAL * 1000);
    setInterval(refreshRoomStatus, REFRESH_INTERVAL * 1000);
}

window.addEventListener('DOMContentLoaded', setupRoomDashboard);
