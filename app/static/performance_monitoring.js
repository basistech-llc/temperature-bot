// AE-200 and independent network performance chart.

let performanceChart = null;
let performanceSamples = [];
let performanceStartMs = null;
let performanceEndMs = null;
let performanceTruncated = false;

const PERFORMANCE_ENDPOINT = "/api/v1/performance_samples";
const FILTER_COLUMNS = {
  "performance-instance": "instance_id",
  "performance-client": "client_id",
  "performance-type": "sample_type",
  "performance-operation": "operation",
};

function localDateValue(milliseconds) {
  const date = new Date(milliseconds);
  const offset = date.getTimezoneOffset() * 60 * 1000;
  return new Date(milliseconds - offset).toISOString().slice(0, 10);
}

function updateDateInputs() {
  document.getElementById("performance-start").value =
    localDateValue(performanceStartMs);
  document.getElementById("performance-end").value =
    localDateValue(performanceEndMs);
}

function setRange(days) {
  performanceEndMs = Date.now();
  performanceStartMs = performanceEndMs - days * 24 * 60 * 60 * 1000;
  updateDateInputs();
  loadPerformanceSamples();
}

function selectedFilters() {
  return Object.fromEntries(
    Object.entries(FILTER_COLUMNS).map(([elementId, column]) => [
      column,
      document.getElementById(elementId).value,
    ]),
  );
}

function filteredSamples() {
  const filters = selectedFilters();
  return performanceSamples.filter((sample) =>
    Object.entries(filters).every(
      ([column, value]) => !value || sample[column] === value,
    ),
  );
}

function fillFilter(elementId, column) {
  const select = document.getElementById(elementId);
  const selected = select.value;
  const values = [...new Set(performanceSamples.map((row) => row[column]))]
    .filter(Boolean)
    .sort();
  select.replaceChildren(new Option("all", ""));
  values.forEach((value) => select.add(new Option(value, value)));
  if (values.includes(selected)) select.value = selected;
}

function refreshFilters() {
  Object.entries(FILTER_COLUMNS).forEach(([elementId, column]) =>
    fillFilter(elementId, column),
  );
}

function points(samples, predicate, column) {
  return samples
    .filter((sample) => predicate(sample) && sample[column] !== null)
    .map((sample) => [sample.observed_at_ms, sample[column]]);
}

function percentile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return (
    sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)
  );
}

function rollingPercentile(samples, column, fraction, windowSize = 60) {
  const numeric = samples
    .filter((sample) => Number.isFinite(sample[column]))
    .sort((left, right) => left.observed_at_ms - right.observed_at_ms);
  return numeric.map((sample, index) => {
    const start = Math.max(0, index - windowSize + 1);
    const values = numeric.slice(start, index + 1).map((row) => row[column]);
    return [sample.observed_at_ms, percentile(values, fraction)];
  });
}

function series(name, data) {
  return {
    name,
    type: "line",
    showSymbol: data.length < 200,
    connectNulls: false,
    data,
  };
}

function buildPerformanceOption(samples) {
  const ae200 = (sample) => sample.sample_type === "ae200_request";
  const icmp = (sample) => sample.sample_type === "icmp_ping";
  const tcp = (sample) => sample.sample_type === "tcp_reject";
  const ae200Samples = samples.filter(ae200);
  return {
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { top: 80, left: 75, right: 30, bottom: 80 },
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "milliseconds", min: 0 },
    dataZoom: [{ type: "inside" }, { type: "slider" }],
    series: [
      series("AE-200 total", points(samples, ae200, "total_ms")),
      series("AE-200 total p50 (60 samples)", rollingPercentile(ae200Samples, "total_ms", 0.5)),
      series("AE-200 total p95 (60 samples)", rollingPercentile(ae200Samples, "total_ms", 0.95)),
      series("WebSocket connect", points(samples, ae200, "connect_ms")),
      series("AE-200 response", points(samples, ae200, "response_ms")),
      series("ICMP median", points(samples, icmp, "icmp_median_ms")),
      series("TCP reject", points(samples, tcp, "connect_ms")),
    ],
  };
}

function renderPerformanceChart() {
  if (!performanceChart) return;
  const samples = filteredSamples();
  const failures = samples.filter((sample) => !sample.success).length;
  const accepted = samples.filter(
    (sample) => sample.sample_type === "tcp_reject" && sample.outcome === "connected",
  ).length;
  document.getElementById("performance-summary").textContent =
    `${samples.length} samples; ${failures} failures; ` +
    `${accepted} unexpected accepted TCP connections` +
    `${performanceTruncated ? "; result limit reached." : "."}`;

  performanceChart.setOption(buildPerformanceOption(samples), { notMerge: true });
}

function loadPerformanceSamples() {
  const query = new URLSearchParams({
    start_ms: Math.floor(performanceStartMs),
    end_ms: Math.floor(performanceEndMs),
  });
  fetch(`${PERFORMANCE_ENDPOINT}?${query}`)
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((page) => {
      performanceSamples = page.samples;
      performanceTruncated = page.truncated;
      refreshFilters();
      renderPerformanceChart();
    })
    .catch((error) => {
      document.getElementById("performance-summary").textContent =
        `Unable to load performance samples: ${error}`;
    });
}

function datesChanged() {
  const start = document.getElementById("performance-start").value;
  const end = document.getElementById("performance-end").value;
  if (!start || !end) return;
  performanceStartMs = new Date(`${start}T00:00:00`).getTime();
  performanceEndMs = new Date(`${end}T23:59:59.999`).getTime();
  loadPerformanceSamples();
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    const chartElement = document.getElementById("performance-chart");
    if (!chartElement) return;
    performanceChart = echarts.init(
      chartElement,
    );
    document
      .getElementById("performance-day")
      .addEventListener("click", () => setRange(1));
    document
      .getElementById("performance-week")
      .addEventListener("click", () => setRange(7));
    document
      .getElementById("performance-month")
      .addEventListener("click", () => setRange(31));
    document
      .getElementById("performance-start")
      .addEventListener("change", datesChanged);
    document
      .getElementById("performance-end")
      .addEventListener("change", datesChanged);
    Object.keys(FILTER_COLUMNS).forEach((elementId) =>
      document
        .getElementById(elementId)
        .addEventListener("change", renderPerformanceChart),
    );
    window.addEventListener("resize", () => performanceChart.resize());
    setRange(1);
  });
}

if (typeof module !== "undefined") {
  module.exports = { buildPerformanceOption, percentile, rollingPercentile };
}
