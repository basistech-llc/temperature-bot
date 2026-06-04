/**
 * Node.js tests for the fan-speed radio selection logic in unit_speed.js.
 * Run with: node tests/test_unit_speed.js
 *
 * Regression coverage for the "Off jumps back to Auto" bug: an off unit that is
 * holding the Auto (-1) fan speed must select the Off radio, not Auto.
 */
const { fanRadioIdForDevice } = require("../app/static/unit_speed.js");

let passed = 0;
let failed = 0;

function check(label, actual, expected) {
  if (actual === expected) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got "${actual}", expected "${expected}"`);
  }
}

// -- The bug: off unit holding Auto must show Off, not Auto --
check(
  "off + held Auto (-1) -> Off",
  fanRadioIdForDevice({ device_id: 5, drive: 0, fan_speed: -1 }),
  "radio-5-0",
);
check(
  "off + held numbered speed -> Off",
  fanRadioIdForDevice({ device_id: 5, drive: 0, fan_speed: 2 }),
  "radio-5-0",
);
check(
  "drive string 'Off' + held Auto -> Off",
  fanRadioIdForDevice({ device_id: 7, drive: "Off", fan_speed: -1 }),
  "radio-7-0",
);

// -- On states still resolve correctly --
check(
  "on + Auto (-1) -> Auto",
  fanRadioIdForDevice({ device_id: 5, drive: 1, fan_speed: -1 }),
  "radio-5-auto",
);
check(
  "on + numbered speed -> that speed",
  fanRadioIdForDevice({ device_id: 5, drive: 1, fan_speed: 3 }),
  "radio-5-3",
);
check(
  "on + speed via legacy 'speed' field -> that speed",
  fanRadioIdForDevice({ device_id: 9, drive: 1, speed: 4 }),
  "radio-9-4",
);

// -- Missing / falsy drive is treated as off --
check(
  "no drive field -> Off",
  fanRadioIdForDevice({ device_id: 5 }),
  "radio-5-0",
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
