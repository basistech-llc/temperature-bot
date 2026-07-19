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
  computeFitScale,
  createRoomStatusRefresher,
  createStatusRefresher,
  fcuStateRequestBody,
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

if (JSON.stringify(fcuStateRequestBody(9, 4)) ===
    JSON.stringify({ device_id: 9, drive: 1, fan_speed: 4 })) {
  passed++;
} else {
  failed++;
  console.error("FAIL room dashboard high selection must be one FCU request");
}

if (JSON.stringify(fcuStateRequestBody(9, 0)) ===
    JSON.stringify({ device_id: 9, drive: 0 })) {
  passed++;
} else {
  failed++;
  console.error("FAIL room dashboard off selection must preserve fan speed");
}

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
    getElementById: () => null,
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
