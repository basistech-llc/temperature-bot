/**
 * Node.js tests for the scale-to-fit math in room_dashboard.js (computeFitScale).
 * Run with: node tests/test_room_scale.js
 *
 * The per-room HVAC page must never show scrollbars at any viewport size
 * (Carl's request). A JS scaler shrinks the whole dashboard to fit; this covers
 * the pure factor it uses. The invariant that matters most is shrink-only: the
 * scaler must never enlarge content (factor capped at 1), or a roomy page on a
 * big screen would zoom up and look broken. These tests lock that in, plus the
 * "fit the tighter of the two axes" and degenerate-size guards.
 */
const {
  applyControlState,
  computeFitScale,
  pendingControlChanges,
  reconcileControlAvailability,
  recordPendingControl,
  setControlAvailability,
  createRoomStatusRefresher,
  createStatusRefresher,
  requestRoomStatus,
  roomControlEndpoint,
} = require("../app/static/room_dashboard.js");

let passed = 0;
let failed = 0;

function approx(label, actual, expected) {
  if (Math.abs(actual - expected) < 1e-9) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got ${actual}, expected ${expected}`);
  }
}

// Content already fits: never enlarge, factor stays 1. This is the regression
// guard against re-introducing upscaling, which would balloon sparse rooms.
approx("fits with room to spare -> 1", computeFitScale(800, 400, 1000, 1000), 1);
approx("fits exactly -> 1", computeFitScale(1000, 1000, 1000, 1000), 1);

// Content too tall: scale by the height ratio (the binding axis here).
approx("too tall -> height ratio", computeFitScale(800, 2000, 1000, 1000), 0.5);

// Content too wide: scale by the width ratio (the binding axis here).
approx("too wide -> width ratio", computeFitScale(2000, 800, 1000, 1000), 0.5);

// Both axes overflow: pick the smaller (tighter) factor so it fits in both.
approx(
  "both overflow -> tighter axis",
  computeFitScale(2000, 4000, 1000, 1000),
  0.25,
);

// Degenerate sizes (nothing measured yet) must not divide-by-zero or NaN out;
// fit() calls this on first paint before layout settles.
approx("zero height -> 1", computeFitScale(800, 0, 1000, 1000), 1);
approx("zero width -> 1", computeFitScale(0, 400, 1000, 1000), 1);

// Non-positive *available* space: content above the wrapper taller than the
// viewport drives availH negative. Without the guard, Math.min would return a
// negative factor -> scale(-x) flips the content and reintroduces a scrollbar,
// which is exactly the failure this feature exists to prevent.
approx("negative avail height -> 1", computeFitScale(800, 400, 1000, -50), 1);
approx("zero avail width -> 1", computeFitScale(800, 400, 0, 1000), 1);

if (roomControlEndpoint("wall_light", "Hickory & East") ===
    "/api/v1/room/Hickory%20%26%20East/wall_light") {
  passed++;
} else {
  failed++;
  console.error("FAIL room control endpoint must encode the dynamic room key");
}

async function testRoomStatusPolling() {
  let requests = 0;
  const unconfiguredDocument = { querySelector: () => null };
  const refreshRoomStatus = createRoomStatusRefresher(
    () => { requests++; },
    unconfiguredDocument,
  );
  const refreshed = await refreshRoomStatus();
  if (refreshed === false && requests === 0) {
    passed++;
  } else {
    failed++;
    console.error("FAIL unconfigured room must not request room-control status");
  }

  let parsedErrorBody = false;
  try {
    await requestRoomStatus("/room-status", async () => ({
      ok: false,
      status: 404,
      json: async () => { parsedErrorBody = true; return { error: "missing" }; },
    }));
    failed++;
    console.error("FAIL non-OK room status must reject");
  } catch (error) {
    if (error.message === "Room status request failed: 404" && !parsedErrorBody) {
      passed++;
    } else {
      failed++;
      console.error(`FAIL non-OK room status rejection: ${error.message}`);
    }
  }
}

async function testDeviceStatusSingleFlight() {
  let releaseRequest;
  let requests = 0;
  let updates = 0;
  const responseReady = new Promise(resolve => { releaseRequest = resolve; });
  const refreshStatus = createStatusRefresher(
    async () => {
      requests++;
      await responseReady;
      return { ok: true, json: async () => ({ devices: [{ device_id: 1 }] }) };
    },
    devices => { updates += devices.length; },
  );

  const firstRefresh = refreshStatus();
  const overlappingRefresh = await refreshStatus();
  if (overlappingRefresh === false && requests === 1 && updates === 0) {
    passed++;
  } else {
    failed++;
    console.error('FAIL room device status requests must not overlap');
  }
  releaseRequest();
  if (await firstRefresh && updates === 1) {
    passed++;
  } else {
    failed++;
    console.error('FAIL completed room device status must update once');
  }

  let fail = true;
  const retryingRefresh = createStatusRefresher(async () => {
    if (fail) {
      fail = false;
      throw new Error('temporary failure');
    }
    return { ok: true, json: async () => ({ devices: [] }) };
  }, () => {});
  if (await retryingRefresh() === false && await retryingRefresh() === true) {
    passed++;
  } else {
    failed++;
    console.error('FAIL failed device status request must release single-flight');
  }
}

async function testRoomControlStatusSingleFlight() {
  let releaseRequest;
  let requests = 0;
  const responseReady = new Promise(resolve => { releaseRequest = resolve; });
  const documentRef = {
    querySelector: () => ({}),
    querySelectorAll: () => [],
  };
  const refreshRoomStatus = createRoomStatusRefresher(async () => {
    requests++;
    await responseReady;
    return { ok: true, json: async () => ({}) };
  }, documentRef);

  const firstRefresh = refreshRoomStatus();
  const overlaps = await Promise.all(Array.from({ length: 10 }, refreshRoomStatus));
  if (overlaps.every(result => result === false) && requests === 1) {
    passed++;
  } else {
    failed++;
    console.error('FAIL room-control status requests must not overlap');
  }
  releaseRequest();
  await firstRefresh;

  let fail = true;
  const retryingRefresh = createRoomStatusRefresher(async () => {
    if (fail) {
      fail = false;
      throw new Error('temporary failure');
    }
    return { ok: true, json: async () => ({}) };
  }, documentRef);
  if (await retryingRefresh() === false && await retryingRefresh() === true) {
    passed++;
  } else {
    failed++;
    console.error('FAIL failed room-control request must release single-flight');
  }
}

/**
 * Minimal DOM stand-in: enough for applyControlState's selector-based lookups
 * without pulling in a headless browser.
 */
function fakeElement(attributes = {}, { dragging = false } = {}) {
  const classes = new Set();
  return {
    value: null,
    textContent: "",
    disabled: false,
    getAttribute: name => attributes[name] ?? null,
    // A slider reports :active only while a pointer is on it.
    matches: selector => selector === ":active" && dragging,
    classList: {
      add: name => classes.add(name),
      remove: name => classes.delete(name),
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
      contains: name => classes.has(name),
    },
  };
}

function fakeTile(key, kind) {
  const classes = new Set();
  return {
    key,
    getAttribute: name =>
      ({ "data-control-key": key, "data-control-kind": kind })[name] ?? null,
    classList: {
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
      contains: name => classes.has(name),
    },
  };
}

function fakeDocument(elementsBySelector) {
  // Mirrors the real DOM's split: querySelector yields one node or null,
  // querySelectorAll always yields a list.
  return {
    querySelector: selector => {
      const found = elementsBySelector[selector];
      return (Array.isArray(found) ? found[0] : found) ?? null;
    },
    querySelectorAll: selector => {
      const found = elementsBySelector[selector];
      if (!found) {
        return [];
      }
      return Array.isArray(found) ? found : [found];
    },
  };
}

function check(label, condition) {
  if (condition) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}`);
  }
}

function testDimmerState() {
  const slider = fakeElement();
  const valueEl = fakeElement();
  const doc = fakeDocument({
    'input.dimmer-slider[data-control-key="main"]': slider,
    '.dimmer-value[data-control-key="main"]': valueEl,
  });
  applyControlState(doc, { key: "main", kind: "dimmer", switch: "on", level: 42 });
  check("dimmer state moves the slider", slider.value === 42);
  check("dimmer state labels the level", valueEl.textContent === "42%");

  // Mid-drag the poll must not yank the handle back to the server's value.
  const dragging = fakeElement({}, { dragging: true });
  const draggingDoc = fakeDocument({
    'input.dimmer-slider[data-control-key="main"]': dragging,
    '.dimmer-value[data-control-key="main"]': fakeElement(),
  });
  applyControlState(draggingDoc, { key: "main", kind: "dimmer", switch: "on", level: 7 });
  check("a slider being dragged is left alone", dragging.value === null);
}

function testFanState() {
  const buttons = ["off", "low", "medium", "high"].map(speed =>
    fakeElement({ "data-speed": speed }));
  const doc = fakeDocument({
    'button.fan-btn[data-control-key="fan"]': buttons,
  });

  applyControlState(doc, { key: "fan", kind: "fan", switch: "on", speed: "medium" });
  check("running fan lights its speed",
    buttons[2].classList.contains("is-on"));
  check("running fan lights only its speed",
    buttons.filter(b => b.classList.contains("is-on")).length === 1);

  // A stopped fan still reports the speed it last ran at. Trusting `speed` over
  // `switch` here would light a speed button on a fan that is not turning.
  applyControlState(doc, { key: "fan", kind: "fan", switch: "off", speed: "high" });
  check("stopped fan lights Off, not its last speed",
    buttons[0].classList.contains("is-on") && !buttons[3].classList.contains("is-on"));
}

function testSwitchState() {
  const button = fakeElement();
  const doc = fakeDocument({
    'button.wall-btn[data-control-key="inner"]': button,
  });
  applyControlState(doc, { key: "inner", kind: "switch", switch: "on" });
  check("switch on reads ON", button.textContent === "ON");
  check("switch on is highlighted", button.classList.contains("is-on"));

  applyControlState(doc, { key: "inner", kind: "switch", switch: "off" });
  check("switch off reads OFF", button.textContent === "OFF");
  check("switch off is not highlighted", !button.classList.contains("is-on"));
}

// A control the server could not read is absent from the response, so nothing
// should throw when its tile has no matching element either.
function testMissingElements() {
  const doc = fakeDocument({});
  applyControlState(doc, { key: "gone", kind: "dimmer", switch: "on", level: 5 });
  applyControlState(doc, { key: "gone", kind: "fan", switch: "on", speed: "low" });
  applyControlState(doc, { key: "gone", kind: "switch", switch: "on" });
  check("absent control elements are tolerated", true);
}

function testUnavailableControls() {
  const switchButton = fakeElement();
  const fanButton = fakeElement({ "data-speed": "low" });
  const tvButton = fakeElement({ "data-direction": "up" });
  const tiles = [
    fakeTile("pendant-lights", "switch"),
    fakeTile("data-closet-fan", "fan"),
    fakeTile("tv", "tv"),
  ];
  const doc = fakeDocument({
    ".room-control-tile[data-control-key]": tiles,
    '.room-control-tile[data-control-key="pendant-lights"]': tiles[0],
    '.room-control-tile[data-control-key="data-closet-fan"]': tiles[1],
    '.room-control-tile[data-control-key="tv"]': tiles[2],
    'button.wall-btn[data-control-key="pendant-lights"]': switchButton,
    'button.fan-btn[data-control-key="data-closet-fan"]': [fanButton],
    'button.tv-btn[data-control-key="tv"]': [tvButton],
  });

  // Nothing readable at all, as when the hub is unreachable.
  reconcileControlAvailability(doc, []);
  check("unreadable switch tile is marked unavailable",
    tiles[0].classList.contains("control-unavailable"));
  check("unreadable switch says so rather than showing a placeholder",
    switchButton.textContent === "Unavailable");
  check("unreadable switch is disabled", switchButton.disabled === true);
  check("unreadable fan is disabled", fanButton.disabled === true);

  // A TV lift is momentary and never reports state. Judging it by its absence
  // from the response would grey out a control that works perfectly.
  check("tv tile is never marked unavailable",
    !tiles[2].classList.contains("control-unavailable"));
  check("tv button stays enabled", tvButton.disabled === false);

  // The device comes back once someone exposes it on the reachable hub.
  reconcileControlAvailability(doc, [
    { key: "pendant-lights", kind: "switch", switch: "on" },
  ]);
  check("recovered control drops the unavailable mark",
    !tiles[0].classList.contains("control-unavailable"));
  check("recovered control is re-enabled", switchButton.disabled === false);
  check("a still-unreadable sibling stays marked",
    tiles[1].classList.contains("control-unavailable"));
}

function testAbsentAttributes() {
  // A readable device that reported no switch. Treating that as "off" would
  // light the OFF button under a fan that is actually running.
  const fanButtons = ["off", "low", "medium", "high"].map(speed =>
    fakeElement({ "data-speed": speed }));
  const switchButton = fakeElement();
  const slider = fakeElement();
  const valueEl = fakeElement();
  const doc = fakeDocument({
    'button.fan-btn[data-control-key="fan"]': fanButtons,
    'button.wall-btn[data-control-key="sw"]': switchButton,
    'input.dimmer-slider[data-control-key="dim"]': slider,
    '.dimmer-value[data-control-key="dim"]': valueEl,
  });

  applyControlState(doc, { key: "fan", kind: "fan", speed: "medium" });
  check("fan with no switch attribute trusts its reported speed",
    fanButtons[2].classList.contains("is-on") &&
    !fanButtons[0].classList.contains("is-on"));

  applyControlState(doc, { key: "sw", kind: "switch" });
  check("switch with no switch attribute shows unknown, not OFF",
    switchButton.textContent === "—" && !switchButton.classList.contains("is-on"));

  applyControlState(doc, { key: "dim", kind: "dimmer" });
  check("dimmer with no level is left alone rather than snapped to 0%",
    slider.value === null && valueEl.textContent === "");
}

function testPendingControlReconcile() {
  const buttons = ["off", "low", "medium", "high"].map(speed =>
    fakeElement({ "data-speed": speed }));
  const doc = fakeDocument({
    'button.fan-btn[data-control-key="fan"]': buttons,
  });

  // User taps MED: the handler records the intent and lights MED at once.
  recordPendingControl("fan", { speed: "medium" });
  buttons.forEach(b => b.classList.toggle("is-on",
    b.getAttribute("data-speed") === "medium"));
  // The hub has not caught up and still reports the old speed.
  applyControlState(doc, { key: "fan", kind: "fan", switch: "on", speed: "high" });
  check("a lagging poll does not bounce the highlight off the commanded speed",
    buttons[2].classList.contains("is-on") && !buttons[3].classList.contains("is-on"));

  // Once the hub agrees, the pending hold is released and later polls apply.
  applyControlState(doc, { key: "fan", kind: "fan", switch: "on", speed: "medium" });
  applyControlState(doc, { key: "fan", kind: "fan", switch: "on", speed: "high" });
  check("once the hub agrees, later polls are applied again",
    buttons[3].classList.contains("is-on"));

  // A switch command that the device has not yet echoed holds the same way.
  const switchButton = fakeElement();
  const switchDoc = fakeDocument({
    'button.wall-btn[data-control-key="sw"]': switchButton,
  });
  recordPendingControl("sw", { state: "on" });
  applyControlState(switchDoc, { key: "sw", kind: "switch", switch: "off" });
  check("a lagging switch poll does not revert the commanded state",
    switchButton.textContent === "");
  delete pendingControlChanges.sw;
}

function testAvailabilityOnlyWritesOnTransition() {
  // The poll runs every 10s and a command takes a moment. If a poll rewrote
  // `disabled` unconditionally it would re-enable a button mid-command and let
  // a second request reach the hub.
  const button = fakeElement();
  const tile = fakeTile("sw", "switch");
  const doc = fakeDocument({
    ".room-control-tile[data-control-key]": [tile],
    '.room-control-tile[data-control-key="sw"]': tile,
    'button.wall-btn[data-control-key="sw"]': button,
  });

  button.disabled = true;  // a click handler disabled it for its POST
  reconcileControlAvailability(doc, [{ key: "sw", kind: "switch", switch: "on" }]);
  check("a poll leaves an in-flight button disabled", button.disabled === true);

  // A genuine transition still writes.
  reconcileControlAvailability(doc, []);
  check("becoming unavailable still disables and marks the tile",
    tile.classList.contains("control-unavailable") && button.disabled === true);
  button.disabled = true;
  reconcileControlAvailability(doc, [{ key: "sw", kind: "switch", switch: "on" }]);
  check("recovering still re-enables", button.disabled === false);
}

testDimmerState();
testFanState();
testSwitchState();
testMissingElements();
testUnavailableControls();
testAbsentAttributes();
testPendingControlReconcile();
testAvailabilityOnlyWritesOnTransition();

testRoomStatusPolling()
  .then(testDeviceStatusSingleFlight)
  .then(testRoomControlStatusSingleFlight)
  .catch(error => {
    failed++;
    console.error(`FAIL room status polling tests: ${error.message}`);
  })
  .finally(() => {
    console.log(`\n${passed} passed, ${failed} failed`);
    process.exit(failed === 0 ? 0 : 1);
  });
