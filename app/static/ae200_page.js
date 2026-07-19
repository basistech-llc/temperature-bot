// AE-200 diagnostics page: read-only state, timing, and command audit.

const AE200_REFRESH_MS = 60 * 1000;
const AE200_STATUS_FIELDS = {
  drive: "Drive",
  mode: "Mode",
  modeStatus: "ModeStatus",
  fan: "FanSpeed",
  inlet: "InletTemp",
  setTemp: "SetTemp",
  schedule: "Schedule",
  scheduleAvailable: "ScheduleAvail",
  hold: "Hold",
};

function cell(text) {
  const element = document.createElement("td");
  element.textContent = text === undefined || text === null || text === "" ? "--" : text;
  return element;
}

function localTimestamp(milliseconds) {
  return new Date(milliseconds).toLocaleString();
}

function warningText(status) {
  return ["ErrorSign", "FilterSign", "CheckWater"]
    .filter((field) => status[field] && status[field] !== "OFF")
    .map((field) => `${field}=${status[field]}`)
    .join(", ") || "none";
}

function rawStatusCell(unit) {
  const result = document.createElement("td");
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const data = document.createElement("pre");
  summary.textContent = `${Object.keys(unit.status).length} fields`;
  data.textContent = JSON.stringify(unit.status, null, 2);
  details.append(summary, data);
  result.appendChild(details);
  return result;
}

function renderStatus(snapshot) {
  const body = document.querySelector("#ae200-status-table tbody");
  const rows = snapshot.units.map((unit) => {
    const status = unit.status || {};
    const row = document.createElement("tr");
    row.appendChild(cell(`${unit.name} (${unit.device_id})`));
    if (unit.error) {
      const error = cell(unit.error);
      error.colSpan = 11;
      row.appendChild(error);
      return row;
    }
    Object.values(AE200_STATUS_FIELDS).forEach((field) =>
      row.appendChild(cell(status[field])),
    );
    row.appendChild(cell(warningText(status)));
    row.appendChild(rawStatusCell(unit));
    return row;
  });
  body.replaceChildren(...rows);
  document.getElementById("ae200-summary").textContent =
    `${snapshot.controller_host}; ${snapshot.units.length} units; ` +
    `${snapshot.simulator ? "simulator" : "live controller"}; ` +
    `read ${localTimestamp(snapshot.observed_at_ms)}.`;
}

function renderCommands(page) {
  const body = document.querySelector("#ae200-command-table tbody");
  const rows = page.commands.map((command) => {
    const row = document.createElement("tr");
    row.appendChild(cell(localTimestamp(command.requested_at_ms)));
    row.appendChild(cell(command.ae200_device_id));
    row.appendChild(cell(Object.entries(command.request).map(([key, value]) => `${key}=${value}`).join(" ")));
    row.appendChild(cell(command.outcome));
    row.appendChild(cell(command.response_summary));
    row.appendChild(cell(`${command.instance_id}/${command.client_id}`));
    return row;
  });
  if (!rows.length) {
    const empty = document.createElement("tr");
    const message = cell("No commands have been recorded.");
    message.colSpan = 6;
    empty.appendChild(message);
    rows.push(empty);
  }
  body.replaceChildren(...rows);
}

async function loadJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function refreshAe200() {
  try {
    const [snapshot, commands] = await Promise.all([
      loadJson("/api/v1/ae200/status"),
      loadJson("/api/v1/ae200/commands?limit=50"),
    ]);
    renderStatus(snapshot);
    renderCommands(commands);
  } catch (error) {
    document.getElementById("ae200-summary").textContent =
      `Unable to load AE-200 diagnostics: ${error}`;
  }
}

async function loadAe200Performance() {
  const endMs = Date.now();
  const query = new URLSearchParams({
    start_ms: endMs - 24 * 60 * 60 * 1000,
    end_ms: endMs,
    sample_type: "ae200_request",
  });
  const summary = document.getElementById("ae200-performance-summary");
  try {
    const page = await loadJson(`/api/v1/performance_samples?${query}`);
    const chart = echarts.init(document.getElementById("ae200-performance-chart"));
    chart.setOption(buildPerformanceOption(page.samples));
    const failures = page.samples.filter((sample) => !sample.success).length;
    summary.textContent = `${page.samples.length} requests in the last day; ${failures} failures.`;
    window.addEventListener("resize", () => chart.resize());
  } catch (error) {
    summary.textContent = `Unable to load AE-200 performance: ${error}`;
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    refreshAe200();
    loadAe200Performance();
    window.setInterval(refreshAe200, AE200_REFRESH_MS);
  });
}

if (typeof module !== "undefined") {
  module.exports = { warningText };
}
