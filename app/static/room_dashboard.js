// Room dashboard interactivity
const DEBUG = false;
const REFRESH_INTERVAL = 10; // seconds between refreshes
const FAN_SPEED_AUTO = -1; // Auto speed value

// Optimistic UI: when the user changes a unit we reflect the intended state
// immediately rather than waiting for a poll. The backend verifies the AE-200
// read-back before returning success. We hold the optimistic state until a poll
// confirms it or until this backstop elapses. Keyed by device_id.
const PENDING_RECONCILE_MS = 60000;
const pendingChanges = {};   // device_id -> {drive, fan_speed, expiresAt}
const lastDeviceSpeed = {};  // device_id -> last known fan speed (for the "was …" note)

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
        if (!response.ok) {
            throw new Error(result.error || `Request failed (${response.status})`);
        }
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

/** Set drive and fan speed through one verified AE-200 operation. */
async function setFcuState(deviceId, speed) {
    return apiCall(
        '/api/v1/set_fcu_state',
        fcuStateRequestBody(deviceId, speed),
        'The AE-200 did not confirm the requested state.'
    );
}

function fcuStateRequestBody(deviceId, speed) {
    const body = {
        device_id: deviceId,
        drive: speed === 0 ? 0 : 1,
    };
    if (speed !== 0) {
        body.fan_speed = speed;
    }
    return body;
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
 *
 * Deliberately does NOT disable the buttons: a press landing while a previous
 * request is still in flight would otherwise be silently dropped (a disabled
 * button fires no click), stranding the unit in its prior state. The optimistic
 * UI + pending reconciliation already handle rapid presses (last-press-wins),
 * so we only show a spinner on the in-flight button for feedback.
 * @param {number} deviceId - Device ID
 * @param {boolean} isLoading - Whether to show loading state
 * @param {HTMLElement|null} activeButton - Button to show spinner on (if loading)
 */
function setDeviceLoading(deviceId, isLoading, activeButton = null) {
    const buttons = document.querySelectorAll(`button.speed-btn[data-device-id="${deviceId}"]`);
    const statusEl = getDeviceStatusElement(deviceId);

    buttons.forEach(button => {
        if (isLoading && activeButton && button === activeButton) {
            button.classList.add('loading');
        } else if (!isLoading) {
            button.classList.remove('loading');
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

    // Reflect the intended state immediately; the poll loop reconciles later.
    applyOptimisticChange(deviceId, speed);

    const handleSuccess = () => refreshStatus();
    // On failure (apiCall already alerts), drop the optimistic state and let a
    // fresh poll restore the true state rather than leaving a wrong highlight.
    const handleError = () => {
        delete pendingChanges[deviceId];
        setDeviceLoading(deviceId, false);
        refreshStatus();
    };

    setFcuState(deviceId, speed)
        .then(handleSuccess)
        .catch(handleError);
}

/**
 * Optimistically reflect a button press before the server round-trip completes.
 * Records the intended state as pending so the poll loop won't revert it until
 * the backend catches up (or the backstop window expires).
 * @param {number} deviceId - Device ID
 * @param {number} clickedSpeed - data-speed of the clicked button (0 = off)
 */
function applyOptimisticChange(deviceId, clickedSpeed) {
    const drive = clickedSpeed === 0 ? 0 : 1;
    // Turning off keeps the last running speed so the "was …" note stays right;
    // selecting a speed sets it directly.
    const speed = clickedSpeed === 0 ? lastDeviceSpeed[deviceId] : clickedSpeed;
    if (drive === 1) {
        lastDeviceSpeed[deviceId] = speed;
    }
    pendingChanges[deviceId] = {
        drive,
        fan_speed: speed,
        expiresAt: Date.now() + PENDING_RECONCILE_MS,
    };
    renderDriveState(deviceId, drive, speed);
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
 * Render a device's one-dimensional drive/speed state: the Off-button "was …"
 * historical note and which button is highlighted. Shared by polled updates and
 * optimistic updates so both paths produce identical UI.
 *
 * In our one-dimensional model the held speed of an off unit is NOT a resume
 * target — it's just history — so it decorates only the (selected) Off button,
 * never a speed button.
 * @param {number} deviceId - Device ID
 * @param {(string|number)} drive - 'Off'/0 when off, otherwise on
 * @param {number} speed - Fan speed (held speed when off; current speed when on)
 */
function renderDriveState(deviceId, drive, speed) {
    const isOff = drive === 'Off' || drive === 0;

    const offBtn = document.querySelector(
        `button.speed-btn.speed-off[data-device-id="${deviceId}"]`);
    if (offBtn) {
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

    const buttons = document.querySelectorAll(
        `button.speed-btn[data-device-id="${deviceId}"]`);
    buttons.forEach(button =>
        updateButtonActiveState(button, { drive, fan_speed: speed }));
}

/**
 * Whether polled device data has caught up to a pending optimistic change.
 * Off matches off regardless of the held speed (it's only historical); an
 * on-state must also match the requested speed.
 * @param {Object} device - Polled device data
 * @param {Object} pending - Pending change {drive, fan_speed}
 * @returns {boolean}
 */
function matchesPending(device, pending) {
    const isOff = device.drive === 'Off' || device.drive === 0;
    const wantOff = pending.drive === 0;
    if (isOff !== wantOff) {
        return false;
    }
    if (wantOff) {
        return true;
    }
    return parseInt(device.fan_speed || device.speed || 0) === pending.fan_speed;
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

        // Drive/speed: reconcile against any pending optimistic change so a
        // not-yet-settled backend read doesn't revert the user's action.
        const incomingSpeed = device.fan_speed || device.speed;
        const pending = pendingChanges[deviceId];
        if (pending && Date.now() < pending.expiresAt && !matchesPending(device, pending)) {
            // Backend hasn't caught up — keep the optimistic state. Crucially,
            // do NOT adopt this lagging speed as lastDeviceSpeed: during fast
            // transitions that would stale-out the Off button's "was …" note.
            renderDriveState(deviceId, pending.drive, pending.fan_speed);
        } else {
            delete pendingChanges[deviceId];
            // Settled: this poll is the source of truth for the held speed.
            lastDeviceSpeed[deviceId] = incomingSpeed;
            renderDriveState(deviceId, device.drive, incomingSpeed);
        }
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

/** Wrap an async operation so calls made while it is running are skipped. */
function createSingleFlight(operation) {
    let inFlight = false;
    return async function runSingleFlight() {
        if (inFlight) {
            return false;
        }
        inFlight = true;
        try {
            return await operation();
        } finally {
            inFlight = false;
        }
    };
}

/** Create a status refresher that permits only one request at a time. */
function createStatusRefresher(request = fetch, update = updateDeviceStatus) {
    return createSingleFlight(async () => {
        try {
            const response = await request('/api/v1/status');
            if (!response.ok) {
                throw new Error(`Status request failed (${response.status})`);
            }
            const data = await response.json();
            if (DEBUG) {
                console.log('Status data received:', data);
            }
            update(data.devices);
            return true;
        } catch (error) {
            console.error('Failed to refresh status:', error);
            return false;
        }
    });
}

const refreshStatus = createStatusRefresher();

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

/** Build a configured-room control endpoint from the dashboard contract. */
function roomControlEndpoint(action, roomKeyOverride = null) {
    const wrapper = typeof document === 'undefined'
        ? null
        : document.getElementById('room-scale-wrap');
    const roomKey = roomKeyOverride === null
        ? (wrapper ? wrapper.dataset.roomControlKey : '')
        : roomKeyOverride;
    return `/api/v1/room/${encodeURIComponent(roomKey)}/${action}`;
}

/**
 * Set a dimmer's level via API.
 * @param {string} control - Configured control key
 * @param {number} level - 0-100
 */
function setDimmerLevel(control, level) {
    apiCall(
        roomControlEndpoint('dimmer'),
        { control, level },
        'Error setting dimmer.'
    );
}

/**
 * Fetch room control status and update UI.
 */
function requestRoomStatus(endpoint, request = fetch) {
    return request(endpoint).then(response => {
        if (!response.ok) {
            throw new Error(`Room status request failed: ${response.status}`);
        }
        return response.json();
    });
}

// Optimistic control state, mirroring the AE-200 speed buttons above: a command
// is reflected the moment it is sent, and the poll loop is not allowed to revert
// it until the backend catches up or this backstop elapses. Hubitat read-back
// can lag a command, which would otherwise bounce a button back and forth for a
// poll or two. Keyed by control key.
const CONTROL_RECONCILE_MS = 60000;
const pendingControlChanges = {};

/**
 * Record the state a control was just commanded into.
 * @param {string} key - Configured control key
 * @param {Object} intent - {state} for a switch, {speed} for a fan
 */
function recordPendingControl(key, intent) {
    pendingControlChanges[key] = {
        ...intent,
        expiresAt: Date.now() + CONTROL_RECONCILE_MS,
    };
}

/** Which fan speed button a polled state should light. */
function activeFanSpeed(state) {
    // A stopped fan still reports the speed it last ran at, so an explicit
    // "off" wins over `speed`. A state with no `switch` at all is a device that
    // did not report one, which is not the same as reporting off.
    return state.switch === 'off' ? 'off' : state.speed;
}

/**
 * Whether a polled state has caught up with the command we last sent.
 * @param {Object} state - One entry from the room_status controls list
 * @param {Object} pending - Recorded intent
 * @returns {boolean}
 */
function controlStateMatchesPending(state, pending) {
    if (pending.state !== undefined) {
        return state.switch === pending.state;
    }
    if (pending.speed !== undefined) {
        return activeFanSpeed(state) === pending.speed;
    }
    return true;
}

/**
 * Apply one control's polled state to its tile.
 *
 * Controls the server could not read are absent from the response entirely, so
 * their tiles keep whatever they last showed rather than being told a state the
 * device never reported. Individual attributes may also be absent, and are
 * likewise left alone rather than defaulted.
 * @param {Document} pageDocument - Document to update
 * @param {Object} state - One entry from the room_status controls list
 */
function applyControlState(pageDocument, state) {
    const pending = pendingControlChanges[state.key];
    if (pending) {
        if (Date.now() < pending.expiresAt && !controlStateMatchesPending(state, pending)) {
            return;  // Backend hasn't caught up; hold the commanded state.
        }
        delete pendingControlChanges[state.key];
    }

    const scope = `[data-control-key="${state.key}"]`;
    if (state.kind === 'dimmer') {
        if (state.level == null) {
            return;
        }
        const slider = pageDocument.querySelector(`input.dimmer-slider${scope}`);
        const valueEl = pageDocument.querySelector(`.dimmer-value${scope}`);
        // Don't yank the handle out from under a finger mid-drag.
        if (slider && !slider.matches(':active')) {
            slider.value = state.level;
        }
        if (valueEl) {
            valueEl.textContent = state.level + '%';
        }
        return;
    }
    if (state.kind === 'fan') {
        const active = activeFanSpeed(state);
        pageDocument.querySelectorAll(`button.fan-btn${scope}`).forEach(button => {
            button.classList.toggle(
                'is-on', button.getAttribute('data-speed') === active);
        });
        return;
    }
    updateSwitchButton(state.key, state.switch, pageDocument);
}

// Every interactive element a control tile can hold. Kept document-scoped (like
// applyControlState) so availability is decided by the same selector contract.
const CONTROL_INPUT_SELECTORS = [
    'button.wall-btn',
    'button.fan-btn',
    'button.tv-btn',
    'input.dimmer-slider',
];

/**
 * Mark one control as readable or not, and disable its inputs when it is not.
 * @param {Document} pageDocument - Document to update
 * @param {string} key - Configured control key
 * @param {boolean} available - Whether the server could read the device
 */
function setControlAvailability(pageDocument, key, available) {
    const scope = `[data-control-key="${key}"]`;
    const tile = pageDocument.querySelector(`.room-control-tile${scope}`);
    const wasUnavailable = tile ? tile.classList.contains('control-unavailable') : false;
    // Only act on a change. Writing `disabled` on every poll would re-enable a
    // button that a click handler had disabled for the duration of its command,
    // letting a second command reach the hub while the first is still in
    // flight.
    if (available !== wasUnavailable) {
        return;
    }
    if (tile) {
        tile.classList.toggle('control-unavailable', !available);
    }
    CONTROL_INPUT_SELECTORS.forEach(selector => {
        pageDocument.querySelectorAll(`${selector}${scope}`).forEach(element => {
            element.disabled = !available;
        });
    });
    if (!available) {
        const button = pageDocument.querySelector(`button.wall-btn${scope}`);
        if (button) {
            button.textContent = 'Unavailable';
        }
    }
}

/**
 * Reconcile every rendered control against the controls the server could read.
 *
 * Called only after a *successful* poll. A failed request means we cannot tell
 * whether the devices are reachable, which is not the same as knowing they are
 * not, so it must leave the tiles alone rather than greying out the whole page
 * on a momentary network blip.
 *
 * TV lifts are momentary and deliberately report no state, so they are never in
 * the response and must not be judged by their absence from it.
 * @param {Document} pageDocument - Document to update
 * @param {Array<Object>} states - The controls list from room_status
 */
function reconcileControlAvailability(pageDocument, states) {
    const readable = new Set(states.map(state => state.key));
    pageDocument
        .querySelectorAll('.room-control-tile[data-control-key]')
        .forEach(tile => {
            if (tile.getAttribute('data-control-kind') === 'tv') {
                return;
            }
            const key = tile.getAttribute('data-control-key');
            setControlAvailability(pageDocument, key, readable.has(key));
        });
}

function createRoomStatusRefresher(request = fetch, documentRef) {
    const pageDocument = documentRef ?? document;
    return createSingleFlight(async () => {
        if (!pageDocument.querySelector('.room-controls-card')) {
            return false;
        }
        try {
            const data = await requestRoomStatus(
                roomControlEndpoint('room_status'),
                request,
            );
            const states = data.controls || [];
            states.forEach(state => applyControlState(pageDocument, state));
            reconcileControlAvailability(pageDocument, states);
            return true;
        } catch (error) {
            if (DEBUG) {
                console.error('Failed to refresh room status:', error);
            }
            return false;
        }
    });
}

const refreshRoomStatus = typeof document === 'undefined'
    ? async () => false
    : createRoomStatusRefresher();

/**
 * Set up every dimmer slider on the page, each addressing its own control.
 */
function setupDimmers() {
    document.querySelectorAll('input.dimmer-slider[data-control-key]').forEach(slider => {
        const control = slider.getAttribute('data-control-key');
        const valueEl = document.querySelector(
            `.dimmer-value[data-control-key="${control}"]`);
        const debouncedSet = debounce(level => setDimmerLevel(control, level), 300);

        slider.addEventListener('input', () => {
            const level = parseInt(slider.value);
            if (valueEl) {
                valueEl.textContent = level + '%';
            }
            debouncedSet(level);
        });
    });
}

/**
 * Update a switch button to reflect current state.
 * @param {string} control - Configured control key
 * @param {string} state - 'on' or 'off'
 * @param {Document} pageDocument - Document to update
 */
function updateSwitchButton(control, state, pageDocument = document) {
    const btn = pageDocument.querySelector(`button.wall-btn[data-control-key="${control}"]`);
    if (!btn) {
        return;
    }
    if (state !== 'on' && state !== 'off') {
        // Readable device that reported no switch attribute. Saying nothing
        // beats asserting OFF for something that may well be on.
        btn.textContent = '—';
        btn.classList.remove('is-on');
        return;
    }
    const isOn = state === 'on';
    btn.textContent = isOn ? 'ON' : 'OFF';
    btn.classList.toggle('is-on', isOn);
}

/**
 * Handle switch button click — toggle on/off.
 * @param {HTMLElement} button - Clicked button element
 */
function handleSwitchButton(button) {
    const control = button.getAttribute('data-control-key');
    const isOn = button.classList.contains('is-on');
    const newState = isOn ? 'off' : 'on';

    // Show the commanded state at once and hold it against the poll loop until
    // the hub's read-back agrees.
    recordPendingControl(control, { state: newState });
    updateSwitchButton(control, newState);

    button.disabled = true;
    apiCall(
        roomControlEndpoint('switch'),
        { control, state: newState },
        'Error toggling switch.'
    ).then(() => {
        button.disabled = false;
    }).catch(() => {
        // The command failed, so stop holding a state the device never took;
        // the next poll restores the truth.
        delete pendingControlChanges[control];
        button.disabled = false;
    });
}

/**
 * Handle fan speed button click.
 * @param {HTMLElement} button - Clicked button element
 */
function handleFanButton(button) {
    const control = button.getAttribute('data-control-key');
    const speed = button.getAttribute('data-speed');
    const siblings = document.querySelectorAll(
        `button.fan-btn[data-control-key="${control}"]`);

    recordPendingControl(control, { speed });
    siblings.forEach(b => {
        b.classList.toggle('is-on', b === button);
        b.disabled = true;
    });

    apiCall(
        roomControlEndpoint('fan'),
        { control, speed },
        'Error setting fan speed.'
    ).then(() => {
        siblings.forEach(b => { b.disabled = false; });
    }).catch(() => {
        delete pendingControlChanges[control];
        siblings.forEach(b => { b.disabled = false; });
    });
}

/**
 * Handle TV control button click.
 * @param {HTMLElement} button - Clicked button element
 */
function handleTvButton(button) {
    const control = button.getAttribute('data-control-key');
    const direction = button.getAttribute('data-direction');
    const buttons = document.querySelectorAll(
        `.tv-btn[data-control-key="${control}"]`);
    buttons.forEach(b => { b.disabled = true; });

    apiCall(
        roomControlEndpoint('tv'),
        { control, direction },
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
 * Largest scale factor <= 1 that fits content (contentW x contentH) inside the
 * available box (availW x availH). Capped at 1 because the scaler only ever
 * shrinks -- enlarging to fill big screens is the responsive CSS's job, and
 * uniform enlargement looks awkward. Returns 1 when content hasn't been measured
 * yet (non-positive dimensions) so we never divide by zero or blow it up.
 *
 * Extracted as a pure function so the shrink-only invariant is unit-testable
 * without a DOM.
 */
function computeFitScale(contentW, contentH, availW, availH) {
    // Bail on any non-positive dimension. Non-positive *available* space happens
    // when content above the wrapper (header + rules banner) is taller than the
    // viewport: availH goes negative, which without this guard would yield a
    // negative scale (flipped content) or scale(0) (invisible). Returning 1
    // leaves the page unscaled; the ResizeObserver refires and self-heals once
    // there is room again.
    if (contentW <= 0 || contentH <= 0 || availW <= 0 || availH <= 0) return 1;
    return Math.min(1, availH / contentH, availW / contentW);
}

/**
 * Scale-to-fit safety: the per-room page must never show scrollbars at any
 * viewport size. Responsive clamp() sizing in the template keeps things
 * attractive across the common range; this scaler is the guarantee that catches
 * the overflow cases (many cards/sensors, very short windows). It only ever
 * shrinks (scale <= 1) -- growing to fill large screens is the CSS's job.
 */
function setupScaleToFit() {
    const wrap = document.getElementById('room-scale-wrap');
    const content = document.getElementById('room-scale-content');
    if (!wrap || !content) return;

    function fit() {
        // CSS transforms don't affect layout, so scrollHeight/scrollWidth always
        // report the natural (unscaled) size regardless of the current transform.
        const contentH = content.scrollHeight;
        const contentW = content.scrollWidth;
        if (!contentH || !contentW) return;
        // Available height: viewport below the wrapper's top edge (which already
        // accounts for any banners/padding above it), minus a small safety margin
        // so sub-pixel rounding never trips a scrollbar.
        const margin = 8;
        const availH = window.innerHeight - wrap.getBoundingClientRect().top - margin;
        const availW = wrap.clientWidth;
        const scale = computeFitScale(contentW, contentH, availW, availH);
        content.style.transform = scale < 1 ? `scale(${scale})` : 'none';
        // Reserve only the scaled height so the page itself doesn't overflow.
        wrap.style.height = (contentH * scale) + 'px';
    }

    window.addEventListener('resize', fit);
    window.addEventListener('orientationchange', fit);
    if (typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(fit);
        // Live data (status text, sensor tiles) resizing the content.
        ro.observe(content);
        // A banner above the wrapper toggling (the rules-off banner in base.html
        // shows/hides post-load) shifts the wrapper down and changes availH, so
        // it must retrigger fit() too.
        const banner = document.getElementById('rules-master-banner');
        if (banner) ro.observe(banner);
    }
    fit();
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

    // Set up dimmers
    setupDimmers();

    // Set up switch buttons
    document.querySelectorAll('.wall-btn[data-control-key]').forEach(button => {
        button.addEventListener('click', () => handleSwitchButton(button));
    });

    // Set up fan speed buttons
    document.querySelectorAll('.fan-btn[data-control-key][data-speed]').forEach(button => {
        button.addEventListener('click', () => handleFanButton(button));
    });

    initializeSensorTemperatures();
    setupTemperatureToggle();
    setupScaleToFit();

    // Initial status refresh
    refreshStatus();
    refreshRoomStatus();

    // Set up periodic refresh
    setInterval(refreshStatus, REFRESH_INTERVAL * 1000);
    setInterval(refreshRoomStatus, REFRESH_INTERVAL * 1000);
}

// Browser-only wiring (skipped under the Node.js test environment).
if (typeof window !== 'undefined') {
    window.addEventListener('DOMContentLoaded', setupRoomDashboard);
}

// Node.js export for testing.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        applyControlState,
        computeFitScale,
        pendingControlChanges,
        reconcileControlAvailability,
        recordPendingControl,
        setControlAvailability,
        createRoomStatusRefresher,
        createStatusRefresher,
        fcuStateRequestBody,
        refreshRoomStatus,
        requestRoomStatus,
        roomControlEndpoint,
    };
}
