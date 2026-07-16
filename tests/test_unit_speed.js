/**
 * Node.js tests for the fan-speed radio selection logic in unit_speed.js.
 * Run with: node tests/test_unit_speed.js
 *
 * Regression coverage for the "Off jumps back to Auto" bug: an off unit that is
 * holding the Auto (-1) fan speed must select the Off radio, not Auto.
 */
global.TemperatureUtils = require("../app/static/temperature_utils.js");

const {
  collectFcuTempSourceChanges,
  autoSetTempRangeForDevice,
  compactAgeFromSeconds,
  clearPendingFanChange,
  cancelDeviceRenamePopup,
  createSingleFlight,
  dashboardAirQualityDeviceIsActive,
  deviceDisplayNameChanged,
  deviceRenameIsSaving,
  deviceLabelWithIcon,
  deviceDisplayNamePatchBody,
  deviceRulesEnabledValue,
  deviceUpdateText,
  deviceUpdateTooltipText,
  deviceUpdateTimestampSeconds,
  enableRulesForDevice,
  ensureModeSelectOption,
  fanRadioIdForDevice,
  FCU_MODE_OPTIONS,
  fcuTempSourcesTitle,
  isAutoOperationMode,
  isFanOperationMode,
  markRangePending,
  markSingleSetTempPending,
  modeLabelForDevice,
  modeValueForDevice,
  setTempDisabledTooltip,
  normalizeSetRange,
  oldestUpdateTimestampForTable,
  parseFcuTempSourceMultiplier,
  pendingRangeUpdateDecision,
  pendingSingleSetTempUpdateDecision,
  renderDisableCell,
  renderAutoSetTempRange,
  refreshOpenFcuTempSources,
  resizeSetRangeEndpoint,
  saveAutoSetTempWidget,
  saveFcuTempSourceMultipliers,
  secondsUntilStatusRefresh,
  setAutoSetTempUnavailable,
  setRangePartFromPointerTarget,
  sortedFcuTempSources,
  submitDeviceDisplayName,
  tableUpdateSummaryText,
  updateSetTempForDevice,
  updateTemperatureCell,
  updateSetRangeModeState,
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

function checkContains(label, actual, expectedFragment) {
  if (String(actual).includes(expectedFragment)) {
    passed++;
  } else {
    failed++;
    console.error(
      `FAIL ${label}: got "${actual}", expected to include "${expectedFragment}"`,
    );
  }
}

function fakeClassList() {
  const classes = new Set();
  return {
    add(className) {
      classes.add(className);
    },
    contains(className) {
      return classes.has(className);
    },
    remove(className) {
      classes.delete(className);
    },
    toggle(className, enabled) {
      if (enabled) {
        classes.add(className);
      } else {
        classes.delete(className);
      }
    },
  };
}

function fakeWidget() {
  return {
    attributes: {},
    classList: fakeClassList(),
    dataset: {},
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
  };
}

async function testSingleFlightStatusRefresh() {
  let releaseFirst;
  let calls = 0;
  const firstOperation = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const runSingleFlight = createSingleFlight();

  const firstRun = runSingleFlight(async () => {
    calls++;
    await firstOperation;
  });
  const overlappingRuns = await Promise.all(
    Array.from({ length: 10 }, () => runSingleFlight(async () => { calls++; })),
  );
  check(
    "forced refresh attempts are skipped while status is pending",
    overlappingRuns.every(result => result === false),
    true,
  );
  check("only one status refresh starts", calls, 1);

  releaseFirst();
  check("first status refresh completes", await firstRun, true);
  check(
    "status refresh can run after completion",
    await runSingleFlight(async () => {
      calls++;
    }),
    true,
  );
  check("second sequential status refresh starts", calls, 2);

  let failureCalls = 0;
  try {
    await runSingleFlight(async () => {
      failureCalls++;
      throw new Error("temporary failure");
    });
  } catch (error) {
    check("single-flight preserves operation errors", error.message, "temporary failure");
  }
  check(
    "failed status refresh releases single-flight",
    await runSingleFlight(async () => { failureCalls++; }),
    true,
  );
  check("retry runs after failed status refresh", failureCalls, 2);
}

check(
  "initial status refresh is immediate",
  secondsUntilStatusRefresh(20_000, 0, false),
  0,
);
check(
  "completed status refresh waits one interval",
  secondsUntilStatusRefresh(20_000, 20_000, false),
  10,
);
check(
  "forced status refresh is immediate",
  secondsUntilStatusRefresh(20_000, 20_000, true),
  0,
);

function testPendingFanChangeOwnership() {
  const pendingChanges = new Map();
  const olderChange = { radioId: "radio-7-4" };
  const newerChange = { radioId: "radio-7-0" };
  pendingChanges.set(7, newerChange);

  clearPendingFanChange(pendingChanges, 7, olderChange);
  check(
    "older request cannot clear newer pending fan selection",
    pendingChanges.get(7),
    newerChange,
  );
  clearPendingFanChange(pendingChanges, 7, newerChange);
  check("owning request clears pending fan selection", pendingChanges.has(7), false);
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
check(
  "pending Off selection is not overwritten by stale High status",
  fanRadioIdForDevice(
    { device_id: 7, drive: 1, fan_speed: 4 },
    "radio-7-0",
  ),
  "radio-7-0",
);

// -- Table update timestamps --
check(
  "device update timestamp uses logtime plus duration",
  deviceUpdateTimestampSeconds({ logtime: 1000, duration: 60 }),
  1060,
);
check(
  "device update timestamp defaults missing duration",
  deviceUpdateTimestampSeconds({ logtime: "1000" }),
  1001,
);
check(
  "oldest FCU update ignores other tables",
  oldestUpdateTimestampForTable(
    [
      { device_type: "ERV", logtime: 900, duration: 1 },
      { device_type: "FCU", logtime: 1000, duration: 60 },
      { device_type: "FCU", logtime: 1100, duration: 20 },
    ],
    "fcu",
  ),
  1060,
);
check(
  "fresh air quality device is included",
  dashboardAirQualityDeviceIsActive(
    { has_speed_control: false, temp10x: 220, logtime: 1000, duration: 60 },
    new Date(1300 * 1000),
  ),
  true,
);
check(
  "expired air quality device is hidden",
  dashboardAirQualityDeviceIsActive(
    { has_speed_control: false, temp10x: 220, logtime: 1000, duration: 60 },
    new Date((1060 + 31 * 24 * 60 * 60) * 1000),
  ),
  false,
);
check(
  "oldest air quality update ignores expired devices",
  oldestUpdateTimestampForTable(
    [
      {
        device_name: "Expired Air",
        has_speed_control: false,
        temp10x: 220,
        logtime: 2000 - 31 * 24 * 60 * 60,
        duration: 1,
      },
      {
        device_name: "Current Air",
        has_speed_control: false,
        temp10x: 230,
        logtime: 2000,
        duration: 20,
      },
    ],
    "air-quality",
    new Date(2200 * 1000),
  ),
  2020,
);
check(
  "compact age minutes",
  compactAgeFromSeconds(240),
  "4m",
);
checkContains(
  "table update summary includes compact age",
  tableUpdateSummaryText(1060, new Date(1300 * 1000)),
  " - 4m ago)",
);
checkContains(
  "table update summary includes source device",
  tableUpdateSummaryText(1060, new Date(1300 * 1000), "Older FCU"),
  " from Older FCU)",
);
checkContains(
  "device update text includes compact age",
  deviceUpdateText(
    { device_name: "Area 51", logtime: 1000, duration: 60 },
    new Date(1300 * 1000),
  ),
  " - 4m ago",
);
checkContains(
  "device update tooltip includes device name",
  deviceUpdateTooltipText(
    { device_name: "Area 51", logtime: 1000, duration: 60 },
    "",
    new Date(1300 * 1000),
  ),
  "Area 51",
);
checkContains(
  "device update tooltip includes update age",
  deviceUpdateTooltipText(
    { device_name: "Area 51", logtime: 1000, duration: 60 },
    "",
    new Date(1300 * 1000),
  ),
  " - 4m ago",
);
check(
  "device update tooltip falls back to device name without timestamp",
  deviceUpdateTooltipText({}, "Fallback Device"),
  "Fallback Device",
);

// -- Rules disabled cell alignment state --
{
  const originalDocument = global.document;
  const cellClasses = new Set(["rules-disabled-active"]);
  const downButtonClasses = new Set();
  const upButtonClasses = new Set();
  const display = {
    attributes: {},
    textContent: "",
    removeAttribute: (name) => {
      delete display.attributes[name];
    },
    setAttribute: (name, value) => {
      display.attributes[name] = value;
    },
  };
  const classListFromSet = (set) => ({
    add: (name) => set.add(name),
    remove: (name) => set.delete(name),
    contains: (name) => set.has(name),
  });
  const cell = {
    classList: classListFromSet(cellClasses),
    querySelectorAll: () => [
      { classList: classListFromSet(downButtonClasses) },
      { classList: classListFromSet(upButtonClasses) },
    ],
  };
  global.document = {
    getElementById: (id) => {
      if (id === "disable-display-44") return display;
      if (id === "disable-for-44") return cell;
      return null;
    },
  };
  try {
    renderDisableCell(44, 0);
    check("enabled rules show centered dash", display.textContent, "—");
    check(
      "enabled rules remove active alignment class",
      cell.classList.contains("rules-disabled-active"),
      false,
    );
    check(
      "enabled rules hide decrement button",
      downButtonClasses.has("hidden"),
      true,
    );

    renderDisableCell(44, Math.floor(Date.now() / 1000) + 90);
    check(
      "disabled rules add active alignment class",
      cell.classList.contains("rules-disabled-active"),
      true,
    );
    check(
      "disabled rules show decrement button",
      downButtonClasses.has("hidden"),
      false,
    );
  } finally {
    global.document = originalDocument;
  }
}

async function testEnableRulesForDevicePost() {
  const originalDocument = global.document;
  const originalFetch = global.fetch;
  const classListFromSet = (set) => ({
    add: (name) => set.add(name),
    remove: (name) => set.delete(name),
    contains: (name) => set.has(name),
  });
  const cellClasses = new Set(["rules-disabled-active"]);
  const badgeClasses = new Set();
  const display = {
    attributes: { "data-disabled-until": "9999999999" },
    textContent: "1:00",
    removeAttribute: (name) => {
      delete display.attributes[name];
    },
    setAttribute: (name, value) => {
      display.attributes[name] = String(value);
    },
  };
  const badge = {
    attributes: { title: "Rules disabled until later" },
    children: ["rules disabled"],
    classList: classListFromSet(badgeClasses),
    replaceChildren(...children) {
      this.children = children;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
  };
  const cell = {
    classList: classListFromSet(cellClasses),
    querySelectorAll: () => [],
  };
  const requests = [];
  global.document = {
    getElementById: (id) => {
      if (id === "disable-display-44") return display;
      if (id === "disable-for-44") return cell;
      if (id === "rules-disabled-44") return badge;
      return null;
    },
  };
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => ({ status: "ok", device_id: 44, disabled_until: 0 }),
    };
  };
  try {
    enableRulesForDevice(44);
    await Promise.resolve();
  } finally {
    global.document = originalDocument;
    global.fetch = originalFetch;
  }

  const body = JSON.parse(requests[0].options.body);
  check("enable rules posts one request", requests.length, 1);
  check(
    "enable rules posts disabled-until endpoint",
    requests[0].url,
    "/api/v1/set_device_disabled_until",
  );
  check("enable rules posts zero disabled_until", body.disabled_until, 0);
  check("enable rules clears display", display.textContent, "—");
  check("enable rules hides badge", badgeClasses.has("hidden"), true);
  check(
    "enable rules removes active alignment class",
    cellClasses.has("rules-disabled-active"),
    false,
  );
}

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
check("fan mode token is fan operation", isFanOperationMode("fan"), true);
check("cool mode token is not fan operation", isFanOperationMode("COOL"), false);
check(
  "dry mode set temperature tooltip",
  setTempDisabledTooltip("dry"),
  "control disabled in Dry mode.",
);
check(
  "fan mode set temperature tooltip",
  setTempDisabledTooltip("FAN"),
  "control disabled in Fan mode.",
);
check("cool mode has no set temperature tooltip", setTempDisabledTooltip("COOL"), "");

const coolSetRangeWidget = fakeWidget();
updateSetRangeModeState(coolSetRangeWidget, "COOL");
check(
  "non-auto rule set range has no hatch",
  coolSetRangeWidget.classList.contains("setrange-widget-local"),
  false,
);
checkContains(
  "non-auto rule set range title names local rules",
  coolSetRangeWidget.attributes.title,
  "local rules",
);

const autoSetRangeWidget = fakeWidget();
updateSetRangeModeState(autoSetRangeWidget, "AUTO");
check(
  "auto rule set range has no hatch",
  autoSetRangeWidget.classList.contains("setrange-widget-local"),
  false,
);
checkContains(
  "auto rule set range title names local rules",
  autoSetRangeWidget.attributes.title,
  "local rules",
);

const lcAutoSetRangeWidget = fakeWidget();
updateSetRangeModeState(lcAutoSetRangeWidget, "LC_AUTO");
check(
  "lc_auto rule set range has no hatch",
  lcAutoSetRangeWidget.classList.contains("setrange-widget-local"),
  false,
);
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
  "FCU source title includes unit name",
  fcuTempSourcesTitle("Area 51"),
  "Area 51: FCU Temperature Sources",
);
check(
  "FCU source title without unit name",
  fcuTempSourcesTitle(""),
  "FCU Temperature Sources",
);
check("FCU label has fan icon", deviceLabelWithIcon("Area 51", "FCU"), "Area 51 🌀");
check("sensor label has sensor icon", deviceLabelWithIcon("Wave", "SENSOR"), "Wave 📡");
check(
  "active air-quality label with unknown type has sensor icon",
  deviceLabelWithIcon("Wave", null, true),
  "Wave 📡",
);
check(
  "inactive label with unknown type has no sensor icon",
  deviceLabelWithIcon("Wave", null, false),
  "Wave",
);
check(
  "sensor label does not duplicate its existing icon",
  deviceLabelWithIcon("Wave 📡", "SENSOR"),
  "Wave 📡",
);
check("ERV label has exchange icon", deviceLabelWithIcon("ERV 1", "ERV"), "ERV 1 ♻️");

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
check(
  "FCU temperature sources show only sources assigned to its room",
  sortedFcuTempSources(
    [
      { source_device_id: 1, room_id: 2, is_stale: false },
      { source_device_id: 2, room_id: 3, is_stale: true },
      { source_device_id: 3, is_stale: false },
    ],
    2,
  )
    .map((source) => source.source_device_id)
    .join(","),
  "1",
);
check(
  "blank room id does not filter FCU temperature sources",
  sortedFcuTempSources(
    [
      { source_device_id: 1, room_id: null, is_stale: false },
      { source_device_id: 2, room_id: 3, is_stale: false },
    ],
    " ",
  ).length,
  2,
);
check(
  "numeric room filter excludes unassigned sources",
  sortedFcuTempSources(
    [
      { source_device_id: 1, room_id: null, is_stale: false },
      { source_device_id: 2, room_id: 3, is_stale: false },
    ],
    "3",
  ).map((source) => source.source_device_id).join(","),
  "2",
);
const originalDocumentForRoomRefresh = global.document;
let refreshedTrigger = null;
const tempSourcesTrigger = { dataset: { deviceId: "12" } };
global.document = {
  getElementById: () => ({
    dataset: { deviceId: "12" },
    classList: { contains: () => false },
  }),
  querySelector: () => tempSourcesTrigger,
};
check(
  "open FCU temperature sources refresh after assignment change",
  refreshOpenFcuTempSources((trigger) => {
    refreshedTrigger = trigger;
  }),
  true,
);
check(
  "temperature-source refresh uses its FCU trigger",
  refreshedTrigger,
  tempSourcesTrigger,
);
global.document = originalDocumentForRoomRefresh;

async function testFcuTempSourcesRefreshHandlesRejection() {
  const originalDocument = global.document;
  const originalConsoleError = console.error;
  let reported = null;
  global.document = {
    getElementById: () => ({
      dataset: { deviceId: "12" },
      classList: { contains: () => false },
    }),
    querySelector: () => tempSourcesTrigger,
  };
  console.error = (_message, error) => { reported = error; };
  try {
    check(
      "open FCU temperature sources accept an async refresh",
      refreshOpenFcuTempSources(() => Promise.reject(new Error("refresh failed"))),
      true,
    );
    await Promise.resolve();
    await Promise.resolve();
    check(
      "temperature-source refresh reports rejection",
      reported.message,
      "refresh failed",
    );
  } finally {
    global.document = originalDocument;
    console.error = originalConsoleError;
  }
}
check(
  "nonnegative multiplier parses",
  parseFcuTempSourceMultiplier(" 1.5 "),
  1.5,
);
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
check(
  "promoted auto set temp range heat bottom",
  promotedAutoSetTempRange.lowC,
  20,
);
check("promoted auto set temp range cool top", promotedAutoSetTempRange.highC, 25);

function fakeElement(attributes = {}, styles = {}) {
  return {
    attributes: { ...attributes },
    style: { ...styles },
    textContent: "",
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
  };
}

const tooltipCellClasses = new Set(["cell-temp-link"]);
const tooltipCell = {
  attributes: {},
  classList: {
    add(name) {
      tooltipCellClasses.add(name);
    },
    remove(name) {
      tooltipCellClasses.delete(name);
    },
    contains(name) {
      return tooltipCellClasses.has(name);
    },
  },
  dataset: { chartUrl: "/chart?mode=raw&device_ids=12" },
  innerHTML: "",
  removeAttribute(name) {
    delete this.attributes[name];
  },
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  },
  textContent: "",
};
updateTemperatureCell(tooltipCell, 745, {
  age: "1m",
  duration: 60,
  logtime: Math.floor(Date.now() / 1000),
});
checkContains(
  "refreshed chart temperature tooltip keeps graph hint",
  tooltipCell.attributes.title,
  "click to show graph",
);

function fakeSetTempElement(attributes = {}) {
  return {
    attributes: { ...attributes },
    classList: fakeClassList(),
    dataset: {},
    textContent: "",
    querySelectorAll: () => [],
    removeAttribute(name) {
      delete this.attributes[name];
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
  };
}

function withSetTempDocument(callback) {
  const originalDocumentForSetTemp = global.document;
  const downButton = { disabled: false };
  const upButton = { disabled: false };
  const setTempControls = fakeSetTempElement();
  setTempControls.querySelectorAll = (selector) =>
    selector === ".settemp-btn" ? [downButton, upButton] : [];
  const elements = {
    "settemp-12": fakeSetTempElement(),
    "settemp-display-12": fakeSetTempElement(),
    "settemp-controls-12": setTempControls,
    "autosettemp-widget-12": fakeSetTempElement(),
  };
  global.document = {
    getElementById: (id) => elements[id] || null,
  };
  try {
    callback({ ...elements, downButton, upButton });
  } finally {
    global.document = originalDocumentForSetTemp;
  }
}

withSetTempDocument(
  ({
    "settemp-12": cell,
    "settemp-display-12": display,
    "settemp-controls-12": controls,
    "autosettemp-widget-12": autoWidget,
    downButton,
    upButton,
  }) => {
    updateSetTempForDevice({
      device_id: 12,
      mode: "FAN",
      set_temp_c: 22,
      logtime: Math.floor(Date.now() / 1000),
    });
    check("fan mode set temp display remains visible", display.textContent, "22.0");
    check(
      "fan mode set temp display is aria disabled",
      display.attributes["aria-disabled"],
      "true",
    );
    check(
      "fan mode set temp controls get disabled class",
      controls.classList.contains("settemp-disabled"),
      true,
    );
    check("fan mode set temp down button disabled", downButton.disabled, true);
    check("fan mode set temp up button disabled", upButton.disabled, true);
    check("fan mode set temp cell tooltip", cell.attributes.title, "control disabled in Fan mode.");

    updateSetTempForDevice({
      device_id: 12,
      mode: "DRY",
      set_temp_c: 22,
      logtime: Math.floor(Date.now() / 1000),
    });
    check("dry mode set temp down button disabled", downButton.disabled, true);
    check("dry mode set temp up button disabled", upButton.disabled, true);
    check("dry mode set temp cell tooltip", cell.attributes.title, "control disabled in Dry mode.");

    autoWidget.dataset.dragging = "true";
    updateSetTempForDevice({ device_id: 12, mode: "AUTO" });
    check("auto mode clears set temp cell tooltip", cell.attributes.title, undefined);

    updateSetTempForDevice({
      device_id: 12,
      mode: "COOL",
      set_temp_c: 22,
      logtime: Math.floor(Date.now() / 1000),
    });
    check(
      "cool mode set temp display is aria enabled",
      display.attributes["aria-disabled"],
      undefined,
    );
    check(
      "cool mode set temp controls lose disabled class",
      controls.classList.contains("settemp-disabled"),
      false,
    );
    check("cool mode set temp down button enabled", downButton.disabled, false);
    check("cool mode set temp up button enabled", upButton.disabled, false);
    check("cool mode clears set temp cell tooltip", cell.attributes.title, undefined);
  },
);

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
check(
  "auto unavailable clears heat data",
  autoWidget.attributes["data-heat-set-temp-c"],
  undefined,
);
check(
  "auto unavailable clears cool data",
  autoWidget.attributes["data-cool-set-temp-c"],
  undefined,
);
check("auto unavailable clears title", autoWidget.attributes.title, undefined);
check("auto unavailable clears fill left", autoFill.style.left, "");
check("auto unavailable clears fill width", autoFill.style.width, "");
check("auto unavailable clears heat handle", autoHeatHandle.style.left, "");
check("auto unavailable clears cool handle", autoCoolHandle.style.left, "");
check("auto unavailable clears heat label", autoLabels[0].textContent, "--");
check(
  "auto unavailable clears cool label data",
  autoLabels[1].attributes["data-temp-c"],
  undefined,
);

async function testAutoSetTempSavePost() {
  const fill = fakeElement({}, { left: "", width: "" });
  const heatHandle = fakeElement({}, { left: "" });
  const coolHandle = fakeElement({}, { left: "" });
  const heatLabel = fakeElement();
  const coolLabel = fakeElement();
  const labels = [heatLabel, coolLabel];
  const widget = {
    attributes: {},
    dataset: {
      deviceId: "12",
      updateUrl: "/api/v1/set_auto_temp",
      heatSetTempC: "19",
      coolSetTempC: "24",
      autoMinC: "18",
      autoMaxC: "27",
    },
    querySelector(selector) {
      return {
        "[data-role='auto-range']": fill,
        "[data-role='heat']": heatHandle,
        "[data-role='cool']": coolHandle,
        "[data-role='heat-label']": heatLabel,
        "[data-role='cool-label']": coolLabel,
      }[selector];
    },
    querySelectorAll(selector) {
      return selector === ".autosettemp-end-label" ? labels : [];
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
  };
  const requests = [];
  const originalFetch = global.fetch;
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      json: async () => ({
        heat_set_temp_c: 20,
        cool_set_temp_c: 25,
      }),
    };
  };
  try {
    await saveAutoSetTempWidget(widget);
  } finally {
    global.fetch = originalFetch;
  }

  const body = JSON.parse(requests[0].options.body);
  check("auto set temp save sends one request", requests.length, 1);
  check("auto set temp save posts endpoint", requests[0].url, "/api/v1/set_auto_temp");
  check("auto set temp save uses POST", requests[0].options.method, "POST");
  check(
    "auto set temp save sends Heat and Cool",
    JSON.stringify(body),
    JSON.stringify({
      device_id: 12,
      heat_set_temp_c: 19,
      cool_set_temp_c: 24,
    }),
  );
  check("auto set temp save updates heat dataset", widget.dataset.heatSetTempC, "20");
  check("auto set temp save updates cool dataset", widget.dataset.coolSetTempC, "25");
  check("auto set temp save clears saving flag", widget.dataset.saving, undefined);
  check("auto set temp save remains pending", widget.dataset.updateState, "pending");
  check("auto set temp save retargets pending heat", widget.dataset.pendingRangeLowC, "20");
  check("auto set temp save retargets pending cool", widget.dataset.pendingRangeHighC, "25");
  check("auto heat handle aria value updates", heatHandle.attributes["aria-valuenow"], "20");
  check("auto cool handle aria value updates", coolHandle.attributes["aria-valuenow"], "25");
}

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

function fakeDeviceRenamePopup(displayName = "East Lab") {
  const message = { textContent: "" };
  const renameButton = { disabled: false };
  const inputs = {
    "device-rename-device-name": { disabled: false, readOnly: true },
    "device-rename-display-name": {
      disabled: false,
      focusCount: 0,
      value: displayName,
      focus() { this.focusCount++; },
    },
    "device-rename-device-type": { disabled: false, readOnly: true },
    "device-rename-rules-enabled": { checked: true, disabled: true },
    "device-rename-last-update": { disabled: false, readOnly: true },
  };
  const controls = [...Object.values(inputs), renameButton, { disabled: false }];
  const popup = {
    attributes: {},
    classList: fakeClassList(),
    controls,
    dataset: {
      currentDisplayName: "West Lab",
      deviceId: "12",
      deviceName: "FCU-12",
      deviceType: "FCU",
      rulesEnabled: "true",
    },
    inputs,
    message,
    querySelector(selector) {
      if (selector === "[data-role='message']") return message;
      if (selector === "[data-action='rename-device']") return renameButton;
      return null;
    },
    querySelectorAll: () => controls,
    removeAttribute(name) { delete this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
  return popup;
}

function installDeviceRenameDocument(popup, renderFailure = false) {
  return {
    getElementById(id) {
      if (id === "device-rename-popup") return popup;
      return popup.inputs[id] || null;
    },
    querySelectorAll() {
      if (renderFailure) throw new Error("simulated rendering failure");
      return [];
    },
  };
}

async function testDeviceRenameCompletion() {
  const originalDocument = global.document;
  const originalFetch = global.fetch;
  const originalConsoleError = console.error;
  const popup = fakeDeviceRenamePopup();
  const errors = [];
  let releaseRequest;
  let requestCount = 0;
  global.document = installDeviceRenameDocument(popup, true);
  global.fetch = async () => {
    requestCount++;
    await new Promise((resolve) => { releaseRequest = resolve; });
    return {
      ok: true,
      json: async () => ({ display_name: "East Lab", device_type: "FCU" }),
    };
  };
  console.error = (...args) => errors.push(args.join(" "));

  try {
    const first = submitDeviceDisplayName("East Lab");
    check("device rename enters saving state", deviceRenameIsSaving(popup), true);
    check("device rename marks dialog busy", popup.attributes["aria-busy"], "true");
    check(
      "device rename disables controls",
      popup.controls.every((control) => control.disabled),
      true,
    );
    check("device rename reports pending state", popup.message.textContent, "Saving…");
    check("Escape cannot close pending device rename", cancelDeviceRenamePopup(), false);
    check("duplicate device rename is ignored", await submitDeviceDisplayName("East Lab"), false);
    check("device rename sends one request", requestCount, 1);

    releaseRequest();
    check("device rename succeeds", await first, true);
    check("successful device rename closes popup", popup.classList.contains("hidden"), true);
    check("successful device rename clears saving state", deviceRenameIsSaving(popup), false);
    check(
      "saved device rename distinguishes rendering failure",
      errors.some((message) => message.includes("rename was saved")),
      true,
    );

    popup.classList.remove("hidden");
    check("Escape closes idle device rename", cancelDeviceRenamePopup(), true);
    check("idle device rename is closed", popup.classList.contains("hidden"), true);
  } finally {
    global.document = originalDocument;
    global.fetch = originalFetch;
    console.error = originalConsoleError;
  }
}

async function testDeviceRenameErrorRecovery() {
  const originalDocument = global.document;
  const originalFetch = global.fetch;
  const originalConsoleError = console.error;
  const popup = fakeDeviceRenamePopup("Duplicate");
  global.document = installDeviceRenameDocument(popup);
  global.fetch = async () => ({
    ok: false,
    status: 409,
    statusText: "Conflict",
    json: async () => ({ error: "Display name already exists" }),
  });
  console.error = () => {};

  try {
    check("failed device rename returns false", await submitDeviceDisplayName("Duplicate"), false);
    check("failed device rename stays open", popup.classList.contains("hidden"), false);
    check("failed device rename clears saving state", deviceRenameIsSaving(popup), false);
    check(
      "failed device rename restores editable input",
      popup.inputs["device-rename-display-name"].disabled,
      false,
    );
    check(
      "failed device rename preserves entered name",
      popup.inputs["device-rename-display-name"].value,
      "Duplicate",
    );
    check(
      "failed device rename restores focus",
      popup.inputs["device-rename-display-name"].focusCount,
      1,
    );
    check(
      "failed device rename shows persistence error",
      popup.message.textContent,
      "409 Display name already exists",
    );
  } finally {
    global.document = originalDocument;
    global.fetch = originalFetch;
    console.error = originalConsoleError;
  }
}

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
check(
  "changed source collection filters unchanged rows",
  sourceChanges.changes.length,
  1,
);
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
        selector ===
        ".fcu-temp-source-weight, .fcu-temp-sources-actions button"
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
  "default set temp slider scale is 55F to 85F",
  normalizeSetRange(0, 40),
  12.8,
  29.4,
);
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
check(
  "set range low handle starts drag",
  setRangePartFromPointerTarget({ currentTarget: { dataset: { role: "low" } } }),
  "low",
);
check(
  "set range high handle starts drag",
  setRangePartFromPointerTarget({ currentTarget: { dataset: { role: "high" } } }),
  "high",
);
check(
  "set range middle fill does not start drag",
  setRangePartFromPointerTarget({ currentTarget: { dataset: { role: "middle" } } }),
  null,
);
check(
  "set range track does not start drag",
  setRangePartFromPointerTarget({ currentTarget: { dataset: { role: "track" } } }),
  null,
);

// -- Pending set-temperature refresh state --
const pendingSingleDisplay = { dataset: {} };
markSingleSetTempPending(pendingSingleDisplay, 23.9, 1000);
check("single set temp starts pending", pendingSingleDisplay.dataset.updateState, "pending");
check(
  "single set temp stale mismatch is held",
  pendingSingleSetTempUpdateDecision(pendingSingleDisplay, 22.2, 2000),
  "hold",
);
check(
  "single set temp expired mismatch fails",
  pendingSingleSetTempUpdateDecision(pendingSingleDisplay, 22.2, 32001),
  "failed",
);
check("single set temp failed state is red", pendingSingleDisplay.dataset.updateState, "failed");
check(
  "single set temp matching update applies",
  pendingSingleSetTempUpdateDecision(pendingSingleDisplay, 23.95, 33000),
  "apply",
);
check("single set temp matching update clears state", pendingSingleDisplay.dataset.updateState, undefined);

const pendingRangeWidget = { dataset: {} };
markRangePending(pendingRangeWidget, 19, 24, 5000);
check("range set temp starts pending", pendingRangeWidget.dataset.updateState, "pending");
check(
  "range set temp stale mismatch is held",
  pendingRangeUpdateDecision(pendingRangeWidget, 18, 23, 6000),
  "hold",
);
check(
  "range set temp expired mismatch fails",
  pendingRangeUpdateDecision(pendingRangeWidget, 18, 23, 36001),
  "failed",
);
check("range set temp failed state is red", pendingRangeWidget.dataset.updateState, "failed");
check(
  "range set temp matching update applies",
  pendingRangeUpdateDecision(pendingRangeWidget, 19.05, 24.05, 37000),
  "apply",
);
check("range set temp matching update clears state", pendingRangeWidget.dataset.updateState, undefined);

Promise.resolve()
  .then(testPendingFanChangeOwnership)
  .then(testSingleFlightStatusRefresh)
  .then(testFcuTempSourcesRefreshHandlesRejection)
  .then(testEnableRulesForDevicePost)
  .then(testFcuBatchSavePost)
  .then(testAutoSetTempSavePost)
  .then(testDeviceRenameCompletion)
  .then(testDeviceRenameErrorRecovery)
  .catch((error) => {
    failed++;
    console.error(error);
  })
  .finally(() => {
    console.log(`\n${passed} passed, ${failed} failed`);
    process.exit(failed === 0 ? 0 : 1);
  });
