"use strict";

const assert = require("assert");
const {
  compareSensors,
  deviceRoomRequest,
  longPressTriggered,
  persistRoomName,
  persistSensorRoom,
  restoreSensorPosition,
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

async function testPersistenceTransitions() {
  const requests = [];
  const successfulRequest = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ room_name: "Bravo" }) };
  };
  await persistSensorRoom(42, 7, successfulRequest);
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0].url, "/api/v1/update_device_room");
  assert.deepStrictEqual(JSON.parse(requests[0].options.body), {
    device_id: 42,
    room_id: 7,
  });

  const renamed = await persistRoomName(7, "Bravo", successfulRequest);
  assert.strictEqual(renamed.room_name, "Bravo");
  assert.strictEqual(requests[1].url, "/api/v1/rooms/7");
  assert.deepStrictEqual(JSON.parse(requests[1].options.body), {
    room_name: "Bravo",
  });

  await assert.rejects(
    persistRoomName(7, "Alpha", async () => ({
      ok: false,
      json: async () => ({ error: "Room name already exists" }),
    })),
    /Room name already exists/,
  );

  const row = {
    dataset: { roomId: "7" },
    parentElement: {
      insertBefore(movedRow, nextRow) {
        assert.strictEqual(movedRow, row);
        assert.strictEqual(nextRow, originalNextRow);
      },
    },
  };
  const originalSeparator = { dataset: { roomId: "3" } };
  const originalNextRow = {};
  restoreSensorPosition(row, originalSeparator, originalNextRow);
  assert.strictEqual(row.dataset.roomId, "3");
}

testPersistenceTransitions()
  .then(() => console.log("room_matrix tests passed"))
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
