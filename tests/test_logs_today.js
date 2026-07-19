global.window = { addEventListener: () => {} };

const {
  changelogActionLabel,
  formatChangelogValue,
} = require("../app/static/logs_today.js");

let passed = 0;
let failed = 0;

function check(label, actual, expected) {
  if (actual === expected) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got ${actual}, expected ${expected}`);
  }
}

check("fan-speed action", changelogActionLabel("fan_speed"), "Fan speed");
check(
  "rules action",
  changelogActionLabel("rules_suspension"),
  "Rules suspension",
);
check("legacy action", changelogActionLabel(null), "Legacy change");
check("ordinary value", formatChangelogValue("fan_speed", 4), "4");
check(
  "zero suspension",
  formatChangelogValue("rules_suspension", 0),
  "Rules enabled",
);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
