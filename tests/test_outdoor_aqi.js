"use strict";

const assert = require("assert");
const { formatAqiObservedAt } = require("../app/static/outdoor_aqi.js");

// Use the local Date implementation while asserting a stable structural format.
assert.match(formatAqiObservedAt(0), /^1969-12-31|^1970-01-01/);
assert.strictEqual(formatAqiObservedAt(null), "");
assert.strictEqual(formatAqiObservedAt("not-a-time"), "");

console.log("outdoor_aqi.js tests passed");
