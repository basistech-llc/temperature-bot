"use strict";

const assert = require("assert");
const { warningText } = require("../app/static/ae200_page.js");

assert.strictEqual(warningText({ ErrorSign: "OFF" }), "none");
assert.strictEqual(
  warningText({ ErrorSign: "ON", FilterSign: "ON", CheckWater: "OFF" }),
  "ErrorSign=ON, FilterSign=ON",
);

console.log("ae200_page.js tests passed");
