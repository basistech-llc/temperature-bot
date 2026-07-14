"use strict";

const assert = require("assert");
const {
  compareSensors,
  deviceRoomRequest,
  longPressTriggered,
  roomHumidityText,
  roomIdFromValue,
  roomNameSortKey,
  roomTemperatureC,
} = require("../app/static/room_matrix.js");

assert.strictEqual(roomIdFromValue(""), null);
assert.strictEqual(roomIdFromValue(null), null);
assert.strictEqual(roomIdFromValue("17"), 17);
assert.strictEqual(roomIdFromValue("not-a-room"), null);

assert.deepStrictEqual(deviceRoomRequest("42", "7"), {
  device_id: 42,
  room_id: 7,
});
assert.deepStrictEqual(deviceRoomRequest(42, ""), {
  device_id: 42,
  room_id: null,
});

assert.strictEqual(longPressTriggered(649, 0), false);
assert.strictEqual(longPressTriggered(650, 10), true);
assert.strictEqual(longPressTriggered(800, 11), false);

assert.strictEqual(roomTemperatureC(215), 21.5);
assert.strictEqual(roomTemperatureC(null), null);
assert.strictEqual(roomTemperatureC(undefined), null);
assert.strictEqual(roomHumidityText(42.6), "43%");
assert.strictEqual(roomHumidityText(undefined), "--");
assert.strictEqual(roomHumidityText(null), "--");

assert.ok(compareSensors("Alpha", 8, "Bravo", 2) < 0);
assert.ok(compareSensors("bravo", 8, "Bravo", 12) < 0);
assert.ok(compareSensors("Charlie", 1, "Bravo", 12) > 0);

assert.deepStrictEqual(
  ["Unassigned", "bamboo", "Area 51"].sort((left, right) =>
    roomNameSortKey(left).localeCompare(roomNameSortKey(right)),
  ),
  ["Area 51", "bamboo", "Unassigned"],
);

console.log("room_matrix tests passed");
