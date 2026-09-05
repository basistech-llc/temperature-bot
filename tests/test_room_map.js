"use strict";

const assert = require("assert");
global.TemperatureUtils = require("../app/static/temperature_utils.js");
const {
  polygonCenter,
  polygonPoints,
  roomMapEntries,
  roomMapMetricText,
} = require("../app/static/room_map.js");

const polygon = [
  { x: 10, y: 20 },
  { x: 30, y: 20 },
  { x: 20, y: 50 },
];
assert.strictEqual(polygonPoints(polygon), "10,20 30,20 20,50");
assert.deepStrictEqual(polygonCenter(polygon), { x: 20, y: 30 });

const rooms = [
  { room_id: 7, room_name: "Original", fcu_device_id: 42, map: { polygon } },
];
const devices = [
  {
    device_id: 42,
    device_type: "FCU",
    room_id: 7,
    calculated_temp10x: 215,
    calculated_humidity: 42.6,
    mode: "COOL",
  },
];
const entry = roomMapEntries(rooms, devices)[0];
assert.strictEqual(entry.roomId, 7);
assert.strictEqual(entry.calculatedTemp10x, 215);
assert.strictEqual(roomMapMetricText(entry), "21.5°C · 43% · COOL");

const renamed = roomMapEntries([{ ...rooms[0], room_name: "Renamed" }], devices)[0];
assert.strictEqual(renamed.roomId, 7);
assert.deepStrictEqual(renamed.polygon, polygon);
assert.strictEqual(renamed.roomName, "Renamed");

const staleOnly = roomMapEntries(rooms, [{ ...devices[0], calculated_temp10x: null }])[0];
assert.strictEqual(roomMapMetricText(staleOnly), "-- · 43% · COOL");

console.log("room_map tests passed");
