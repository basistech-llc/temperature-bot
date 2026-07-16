"use strict";

function polygonPoints(polygon) {
  return (polygon || []).map((point) => `${Number(point.x)},${Number(point.y)}`).join(" ");
}

function roomMapEntries(rooms, devices) {
  const deviceList = Array.isArray(devices) ? devices : [];
  return (Array.isArray(rooms) ? rooms : []).map((room) => {
    const fcu = deviceList.find(
      (device) =>
        device.device_type === "FCU" &&
        (Number(device.device_id) === Number(room.fcu_device_id) ||
          Number(device.room_id) === Number(room.room_id)),
    );
    return {
      roomId: room.room_id,
      roomName: room.room_name || "Unnamed room",
      polygon: room.map?.polygon || [],
      color: room.map?.color || "#2563eb",
      calculatedTemp10x: fcu?.calculated_temp10x ?? null,
      calculatedHumidity: fcu?.calculated_humidity ?? null,
      state: fcu?.mode || fcu?.drive || fcu?.fan_speed || "--",
    };
  });
}

function roomMapMetricText(entry) {
  const tempC = Number(entry.calculatedTemp10x) / 10;
  const temperature =
    entry.calculatedTemp10x === null || !Number.isFinite(tempC)
      ? "--"
      : TemperatureUtils.formatTemperature(tempC);
  const humidity = Number(entry.calculatedHumidity);
  const humidityText =
    entry.calculatedHumidity === null || !Number.isFinite(humidity)
      ? "--"
      : `${Math.round(humidity)}%`;
  return `${temperature} · ${humidityText} · ${entry.state}`;
}

function polygonCenter(polygon) {
  if (!polygon.length) return { x: 0, y: 0 };
  return {
    x: polygon.reduce((sum, point) => sum + Number(point.x), 0) / polygon.length,
    y: polygon.reduce((sum, point) => sum + Number(point.y), 0) / polygon.length,
  };
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function renderRoomMap(entries) {
  const overlay = document.getElementById("room-map-overlay");
  const unmapped = document.getElementById("room-map-unmapped");
  if (!overlay || !unmapped) return;
  overlay.replaceChildren();
  unmapped.replaceChildren();
  entries.forEach((entry) => {
    if (entry.polygon.length < 3) {
      const item = document.createElement("li");
      item.textContent = entry.roomName;
      unmapped.appendChild(item);
      return;
    }
    const group = svgElement("g", { "data-room-id": entry.roomId });
    group.appendChild(
      svgElement("polygon", {
        points: polygonPoints(entry.polygon),
        fill: entry.color,
        stroke: entry.color,
      }),
    );
    const center = polygonCenter(entry.polygon);
    const name = svgElement("text", { x: center.x, y: center.y - 8, class: "room-map-name" });
    name.textContent = entry.roomName;
    const metrics = svgElement("text", { x: center.x, y: center.y + 18, class: "room-map-metrics" });
    metrics.textContent = roomMapMetricText(entry);
    group.append(name, metrics);
    overlay.appendChild(group);
  });
}

async function loadRoomMap(request = fetch) {
  const [roomsResponse, statusResponse] = await Promise.all([
    request("/api/v1/rooms"),
    request("/api/v1/status"),
  ]);
  if (!roomsResponse.ok || !statusResponse.ok) throw new Error("Unable to load room map.");
  const rooms = await roomsResponse.json();
  const status = await statusResponse.json();
  const entries = roomMapEntries(rooms.rooms, status.devices);
  renderRoomMap(entries);
  const message = document.getElementById("room-map-message");
  if (message) message.textContent = entries.length ? "" : "No rooms are configured.";
  return entries;
}

if (typeof window !== "undefined") {
  window.addEventListener("DOMContentLoaded", () => {
    loadRoomMap().catch((error) => {
      const message = document.getElementById("room-map-message");
      if (message) message.textContent = error.message;
    });
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { polygonCenter, polygonPoints, roomMapEntries, roomMapMetricText };
}
