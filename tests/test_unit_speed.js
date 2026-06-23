/**
 * Node.js tests for the fan-speed radio selection logic in unit_speed.js.
 * Run with: node tests/test_unit_speed.js
 *
 * Regression coverage for the "Off jumps back to Auto" bug: an off unit that is
 * holding the Auto (-1) fan speed must select the Off radio, not Auto.
 */
const {
  collectFcuTempSourceChanges,
  autoSetTempRangeForDevice,
  deviceDisplayNameChanged,
  deviceDisplayNamePatchBody,
  deviceRulesEnabledValue,
  ensureModeSelectOption,
  fanRadioIdForDevice,
  FCU_MODE_OPTIONS,
  fcuTempSourcesTitle,
  isAutoOperationMode,
  modeLabelForDevice,
  modeValueForDevice,
  moveSetRange,
  normalizeSetRange,
  parseFcuTempSourceMultiplier,
  resizeSetRangeEndpoint,
  saveFcuTempSourceMultipliers,
  setAutoSetTempUnavailable,
  sortedFcuTempSources,
} = require("../app/static/unit_speed.js");

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

function checkRange(label, actual, expectedLow, expectedHigh) {
  if (
    actual &&
    actual.lowC === expectedLow &&
    actual.highC === expectedHigh
  ) {
    passed++;
  } else {
    failed++;
    console.error(
      `FAIL ${label}: got ${JSON.stringify(actual)}, expected ${expectedLow}-${expectedHigh}`,
    );
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

// -- AE-200 mode display --
check(
  "mode from promoted field",
  modeLabelForDevice({ mode: "COOL" }),
  "Cool",
);
check(
  "mode from raw status payload",
  modeLabelForDevice({ status: { Mode: "HEAT" } }),
  "Heat",
);
check(
  "mode value is canonical",
  modeValueForDevice({ status: { Mode: "cool" } }),
  "COOL",
);
check(
  "dry mode display label",
  modeLabelForDevice({ mode: "DRY" }),
  "Dry",
);
check(
  "dry mode is commandable",
  FCU_MODE_OPTIONS.includes("DRY"),
  true,
);
check(
  "auto mode is commandable",
  FCU_MODE_OPTIONS.includes("AUTO"),
  true,
);
check("auto mode token is auto operation", isAutoOperationMode("AUTO"), true);
check("lc_auto mode token is auto operation", isAutoOperationMode("LC_AUTO"), true);
check(
  "unknown mode passes through",
  modeLabelForDevice({ mode: "SOMETHING_NEW" }),
  "SOMETHING_NEW",
);
check(
  "missing mode",
  modeLabelForDevice({ status: {} }),
  "--",
);

// -- FCU temperature source popup behavior --
check(
  "temperature source title includes room name",
  fcuTempSourcesTitle("Area 51"),
  "Area 51: Temperature Sources",
);
check(
  "temperature source title without room name",
  fcuTempSourcesTitle(""),
  "Temperature Sources",
);

const unsortedSources = [
  { source_device_id: 1, is_stale: false },
  { source_device_id: 2, is_stale: true },
  { source_device_id: 3, is_stale: false },
  { source_device_id: 4, is_stale: true },
];
check(
  "stale temperature sources sort to bottom",
  sortedFcuTempSources(unsortedSources)
    .map((source) => source.source_device_id)
    .join(","),
  "1,3,2,4",
);
check(
  "temperature source sorting does not mutate source list",
  unsortedSources.map((source) => source.source_device_id).join(","),
  "1,2,3,4",
);
check("nonnegative multiplier parses", parseFcuTempSourceMultiplier(" 1.5 "), 1.5);
check("negative multiplier is invalid", parseFcuTempSourceMultiplier("-0.1"), null);

const autoSetTempRange = autoSetTempRangeForDevice({
  status: { SetTemp1: "24", SetTemp2: "19", AutoMin: "18", AutoMax: "27" },
});
check("auto set temp range heat bottom", autoSetTempRange.lowC, 19);
check("auto set temp range cool top", autoSetTempRange.highC, 24);

const promotedAutoSetTempRange = autoSetTempRangeForDevice({
  heat_set_temp_c: 20,
  cool_set_temp_c: 25,
  auto_min_c: 18,
  auto_max_c: 27,
});
check("promoted auto set temp range heat bottom", promotedAutoSetTempRange.lowC, 20);
check("promoted auto set temp range cool top", promotedAutoSetTempRange.highC, 25);

function fakeElement(attributes = {}, styles = {}) {
  return {
    attributes: { ...attributes },
    style: { ...styles },
    textContent: "",
    removeAttribute(name) {
      delete this.attributes[name];
    },
  };
}

const autoFill = fakeElement({}, { left: "20%", width: "50%" });
const autoHeatHandle = fakeElement({}, { left: "20%" });
const autoCoolHandle = fakeElement({}, { left: "70%" });
const autoLabels = [
  fakeElement({ "data-temp-c": "19" }),
  fakeElement({ "data-temp-c": "24" }),
];
autoLabels[0].textContent = "19";
autoLabels[1].textContent = "24";
const autoWidget = {
  attributes: {
    "data-heat-set-temp-c": "19",
    "data-cool-set-temp-c": "24",
    title: "Auto Heat 19°C / Cool 24°C",
  },
  removeAttribute(name) {
    delete this.attributes[name];
  },
  querySelector(selector) {
    return {
      "[data-role='auto-range']": autoFill,
      "[data-role='heat']": autoHeatHandle,
      "[data-role='cool']": autoCoolHandle,
    }[selector];
  },
  querySelectorAll(selector) {
    return selector === ".autosettemp-end-label" ? autoLabels : [];
  },
};
setAutoSetTempUnavailable(autoWidget);
check("auto unavailable clears heat data", autoWidget.attributes["data-heat-set-temp-c"], undefined);
check("auto unavailable clears cool data", autoWidget.attributes["data-cool-set-temp-c"], undefined);
check("auto unavailable clears title", autoWidget.attributes.title, undefined);
check("auto unavailable clears fill left", autoFill.style.left, "");
check("auto unavailable clears fill width", autoFill.style.width, "");
check("auto unavailable clears heat handle", autoHeatHandle.style.left, "");
check("auto unavailable clears cool handle", autoCoolHandle.style.left, "");
check("auto unavailable clears heat label", autoLabels[0].textContent, "--");
check("auto unavailable clears cool label data", autoLabels[1].attributes["data-temp-c"], undefined);

// -- Device display-name rename behavior --
check(
  "unchanged display name does not enable rename",
  deviceDisplayNameChanged("Server Room", "Server Room"),
  false,
);
check(
  "changed display name enables rename",
  deviceDisplayNameChanged("Server Room", "East Lab"),
  true,
);
check(
  "blank display name does not enable rename",
  deviceDisplayNameChanged("Server Room", "   "),
  false,
);
check(
  "display-name PATCH trims and uses API key",
  JSON.stringify(deviceDisplayNamePatchBody(" East Lab ")),
  JSON.stringify({ display_name: "East Lab" }),
);
check("rules-enabled true string parses", deviceRulesEnabledValue("true"), true);
check("rules-enabled false string parses", deviceRulesEnabledValue("false"), false);
check("rules-enabled one parses", deviceRulesEnabledValue(1), true);
check("rules-enabled zero parses", deviceRulesEnabledValue(0), false);

const popupWithChangedSource = {
  querySelectorAll: () => [
    {
      value: "0",
      dataset: {
        fcuDeviceId: "12",
        sourceDeviceId: "20",
        initialMultiplier: "0",
      },
    },
    {
      value: "1.5",
      dataset: {
        fcuDeviceId: "12",
        sourceDeviceId: "21",
        initialMultiplier: "1",
      },
    },
  ],
};
const sourceChanges = collectFcuTempSourceChanges(popupWithChangedSource);
check("changed source collection has no error", sourceChanges.error, "");
check("changed source collection filters unchanged rows", sourceChanges.changes.length, 1);
check(
  "changed source collection builds API payload",
  JSON.stringify(sourceChanges.changes[0]),
  JSON.stringify({ fcu_device_id: 12, source_device_id: 21, multiplier: 1.5 }),
);

const invalidSourceChanges = collectFcuTempSourceChanges({
  querySelectorAll: () => [
    {
      value: "-1",
      dataset: {
        fcuDeviceId: "12",
        sourceDeviceId: "20",
        initialMultiplier: "0",
      },
    },
  ],
});
check(
  "invalid source collection reports validation error",
  invalidSourceChanges.error,
  "Weight must be a nonnegative number.",
);

async function testFcuBatchSavePost() {
  const inputs = [
    {
      disabled: false,
      value: "0",
      dataset: {
        fcuDeviceId: "12",
        sourceDeviceId: "20",
        initialMultiplier: "0",
      },
    },
    {
      disabled: false,
      value: "1.5",
      dataset: {
        fcuDeviceId: "12",
        sourceDeviceId: "21",
        initialMultiplier: "1",
      },
    },
    {
      disabled: false,
      value: "0.25",
      dataset: {
        fcuDeviceId: "12",
        sourceDeviceId: "22",
        initialMultiplier: "0",
      },
    },
  ];
  const buttons = [{ disabled: false }, { disabled: false }, { disabled: false }];
  const message = {
    textContent: "",
    classList: {
      toggle: () => {},
    },
  };
  const popup = {
    dataset: { updateUrl: "/api/v1/fcu_temp_source" },
    classList: {
      hidden: false,
      add: (name) => {
        popup.classList.hidden = name === "hidden";
      },
    },
    querySelector: (selector) =>
      selector === "[data-role='message']" ? message : null,
    querySelectorAll: (selector) => {
      if (selector === ".fcu-temp-source-weight") {
        return inputs;
      }
      if (
        selector === ".fcu-temp-source-weight, .fcu-temp-sources-actions button"
      ) {
        return inputs.concat(buttons);
      }
      return [];
    },
  };
  const requests = [];
  const originalDocumentForSave = global.document;
  const originalFetch = global.fetch;
  global.document = {
    getElementById: (id) => (id === "fcu-temp-sources-popup" ? popup : null),
  };
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => ({ sources: [] }),
    };
  };
  try {
    await saveFcuTempSourceMultipliers();
  } finally {
    global.document = originalDocumentForSave;
    global.fetch = originalFetch;
  }

  const postedBody = JSON.parse(requests[0].options.body);
  check("batch save sends one request", requests.length, 1);
  check("batch save posts update URL", requests[0].url, "/api/v1/fcu_temp_source");
  check("batch save sends changed rows as an array", Array.isArray(postedBody), true);
  check("batch save omits unchanged row", postedBody.length, 2);
  check(
    "batch save sends all changed rows",
    JSON.stringify(postedBody),
    JSON.stringify([
      { fcu_device_id: 12, source_device_id: 21, multiplier: 1.5 },
      { fcu_device_id: 12, source_device_id: 22, multiplier: 0.25 },
    ]),
  );
}

// -- FCU mode select option updates --
const originalDocument = global.document;
global.document = {
  createElement: () => ({
    dataset: {},
    disabled: false,
    textContent: "",
    value: "",
  }),
};
try {
  const unusualMode = 'FAN"] [value="COOL';
  const existingSelect = {
    firstChild: null,
    inserted: false,
    options: [{ value: unusualMode }],
    querySelector: () => {
      throw new Error("querySelector should not be used for mode values");
    },
    insertBefore: () => {
      existingSelect.inserted = true;
    },
  };
  ensureModeSelectOption(existingSelect, unusualMode);
  check(
    "existing unusual mode option does not insert",
    existingSelect.inserted,
    false,
  );

  const newSelect = {
    firstChild: null,
    inserted: null,
    options: [],
    insertBefore: (option) => {
      newSelect.inserted = option;
      newSelect.options.unshift(option);
    },
  };
  ensureModeSelectOption(newSelect, unusualMode);
  check(
    "unusual mode option value is preserved",
    newSelect.inserted.value,
    unusualMode,
  );
  check("unusual mode option is disabled", newSelect.inserted.disabled, true);
} finally {
  global.document = originalDocument;
}

// -- FCU set-range math --
checkRange(
  "too narrow range expands to minimum",
  normalizeSetRange(20, 22, { minRangeC: 3, trackMinC: 10, trackMaxC: 30 }),
  20,
  23,
);
checkRange(
  "lower endpoint cannot cross minimum width",
  resizeSetRangeEndpoint(20, 24, "low", 23, {
    minRangeC: 3,
    trackMinC: 10,
    trackMaxC: 30,
  }),
  21,
  24,
);
checkRange(
  "moving middle preserves width and clamps to track",
  moveSetRange(20, 24, -20, { minRangeC: 3, trackMinC: 10, trackMaxC: 30 }),
  10,
  14,
);

testFcuBatchSavePost()
  .catch((error) => {
    failed++;
    console.error(error);
  })
  .finally(() => {
    console.log(`\n${passed} passed, ${failed} failed`);
    process.exit(failed === 0 ? 0 : 1);
  });
