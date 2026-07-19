// Shared outdoor AQI widget behavior for the Weather and Air Quality pages.

function applyOutdoorAqiColor(widget) {
  const pill = widget.querySelector("[data-aqi-color]");
  if (!pill) return;
  const color = pill.dataset.aqiColor;
  pill.style.backgroundColor = color || "";
  pill.style.color = color ? "#fff" : "";
}

function formatAqiObservedAt(seconds) {
  if (seconds === null || seconds === undefined || seconds === "") return "";
  if (!Number.isFinite(Number(seconds))) return "";
  const date = new Date(Number(seconds) * 1000);
  const pad = (value) => String(value).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

function updateOutdoorAqiWidget(widgetId, aqi, observedAt) {
  const widget = document.getElementById(widgetId);
  if (!widget || !aqi) return;
  widget.querySelector("[data-aqi-value]").textContent =
    Number.isFinite(Number(aqi.value)) ? String(Math.round(Number(aqi.value))) : "--";
  const pill = widget.querySelector("[data-aqi-name]");
  pill.textContent = aqi.name || "";
  pill.dataset.aqiColor = aqi.color || "";
  applyOutdoorAqiColor(widget);

  const asof = widget.querySelector("[data-aqi-asof]");
  const formatted = formatAqiObservedAt(observedAt);
  asof.textContent = formatted ? `Data as of: ${formatted}` : "";
  asof.hidden = !formatted;
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".outdoor-aqi-widget").forEach(applyOutdoorAqiColor);
  });
}

if (typeof module !== "undefined") {
  module.exports = { formatAqiObservedAt };
}
