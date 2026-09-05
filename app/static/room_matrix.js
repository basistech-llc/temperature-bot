"use strict";

const ROOM_LONG_PRESS_MS = 650;
const ROOM_POINTER_SLOP_PX = 10;
const ROOM_SHIFT_MS = 140;
const ROOM_DELETE_CONFIRM_MS = 5000;

function roomIdFromValue(value) {
  const normalized = String(value ?? "").trim();
  if (!normalized) return null;
  const roomId = Number(normalized);
  return Number.isInteger(roomId) ? roomId : null;
}

function deviceRoomRequest(deviceId, roomId) {
  return { device_id: Number(deviceId), room_id: roomIdFromValue(roomId) };
}

async function persistSensorRoom(deviceId, roomId, request = fetch) {
  const response = await request("/api/v1/update_device_room", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(deviceRoomRequest(deviceId, roomId)),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Unable to move sensor.");
  return data;
}

async function persistRoomName(roomId, roomName, request = fetch) {
  const response = await request(`/api/v1/rooms/${roomId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_name: roomName }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Unable to rename room.");
  return data;
}

async function persistNewRoom(roomName, request = fetch) {
  const response = await request("/api/v1/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_name: roomName }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Unable to create room.");
  return data;
}

async function persistRoomDeletion(roomId, request = fetch) {
  const response = await request(`/api/v1/rooms/${roomId}`, { method: "DELETE" });
  if (response.ok) return true;
  const data = await response.json().catch(() => ({}));
  throw new Error(data.error || "Unable to delete room.");
}

function roomDisplayName(roomName, hasFcu) {
  return `${roomName}${String(hasFcu) === "true" ? " 🌀" : ""}`;
}

function roomDeleteCountdown(startedAt, now = Date.now()) {
  const remaining = Math.max(
    0,
    Math.ceil((startedAt + ROOM_DELETE_CONFIRM_MS - now) / 1000),
  );
  return { enabled: remaining === 0, label: remaining ? `OK (${remaining})` : "OK" };
}

function longPressTriggered(elapsedMs, movementPx) {
  return elapsedMs >= ROOM_LONG_PRESS_MS && movementPx <= ROOM_POINTER_SLOP_PX;
}

function roomNameSortKey(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

function roomTemperatureC(temp10x) {
  if (temp10x === null || temp10x === undefined || temp10x === "") return null;
  const value = Number(temp10x);
  return Number.isFinite(value) ? value / 10 : null;
}

function roomHumidityText(humidity) {
  if (humidity === null || humidity === undefined || humidity === "") return "--";
  const value = Number(humidity);
  return Number.isFinite(value) ? `${Math.round(value)}%` : "--";
}

function compareSensors(leftName, leftId, rightName, rightId) {
  const nameOrder = roomNameSortKey(leftName).localeCompare(roomNameSortKey(rightName));
  return nameOrder || Number(leftId) - Number(rightId);
}

function nextRoomSeparator(row) {
  let candidate = row.nextElementSibling;
  while (candidate && !candidate.classList.contains("room-separator")) {
    candidate = candidate.nextElementSibling;
  }
  return candidate;
}

function separatorForRow(row) {
  let candidate = row;
  while (candidate && !candidate.classList.contains("room-separator")) {
    candidate = candidate.previousElementSibling;
  }
  return candidate;
}

function insertRowInRoom(row, separator) {
  const nextSeparator = nextRoomSeparator(separator);
  separator.parentElement.insertBefore(row, nextSeparator);
  row.dataset.roomId = separator.dataset.roomId || "";
}

function restoreSensorPosition(row, separator, nextRow) {
  row.parentElement.insertBefore(row, nextRow);
  row.dataset.roomId = separator?.dataset.roomId || "";
}

function showRoomMatrixMessage(message, isError = false) {
  const element = document.getElementById("room-matrix-message");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.remove("hidden");
  clearTimeout(element._hideTimer);
  element._hideTimer = setTimeout(() => element.classList.add("hidden"), 4500);
}

function clearDropTargets() {
  document.querySelectorAll(".room-drop-target").forEach((row) => {
    row.classList.remove("room-drop-target");
  });
}

function animatePlaceholderMove(placeholder, beforeRow, tbody = beforeRow?.parentElement) {
  if (
    !tbody ||
    (placeholder.parentElement === tbody && placeholder.nextElementSibling === beforeRow)
  ) return;
  const rows = [...tbody.querySelectorAll(".room-separator, .room-sensor-row")]
    .filter((row) => row !== placeholder && !row.classList.contains("room-dragging"));
  const oldTops = new Map(rows.map((row) => [row, row.getBoundingClientRect().top]));
  tbody.insertBefore(placeholder, beforeRow);
  rows.forEach((row) => {
    const offset = oldTops.get(row) - row.getBoundingClientRect().top;
    if (!offset) return;
    row.style.transition = "none";
    row.style.transform = `translateY(${offset}px)`;
    requestAnimationFrame(() => {
      row.style.transition = `transform ${ROOM_SHIFT_MS}ms ease`;
      row.style.transform = "";
    });
  });
}

function sortedRoomPosition(separator, placeholder) {
  let row = separator.nextElementSibling;
  while (row && !row.classList.contains("room-separator")) {
    if (
      row !== placeholder &&
      !row.classList.contains("room-dragging") &&
      compareSensors(
        placeholder.dataset.sensorName,
        placeholder.dataset.deviceId,
        row.querySelector(".device-name-context")?.dataset.displayName,
        row.dataset.deviceId,
      ) < 0
    ) return row;
    row = row.nextElementSibling;
  }
  return row;
}

function createDragPlaceholder(row) {
  const placeholder = document.createElement("tr");
  placeholder.className = "room-drag-placeholder";
  placeholder.dataset.deviceId = row.dataset.deviceId;
  placeholder.dataset.sensorName = row.querySelector(
    ".device-name-context",
  )?.dataset.displayName || "";
  const cell = document.createElement("td");
  cell.colSpan = row.children.length;
  cell.style.height = `${row.getBoundingClientRect().height}px`;
  placeholder.appendChild(cell);
  return placeholder;
}

function createRowDragImage(row) {
  const table = row.closest("table").cloneNode(false);
  const body = document.createElement("tbody");
  const clone = row.cloneNode(true);
  stripElementIds(clone);
  [...clone.children].forEach((cell, index) => {
    cell.style.width = `${row.children[index].getBoundingClientRect().width}px`;
  });
  table.className = `${row.closest("table").className} room-row-drag-image`;
  table.removeAttribute("id");
  table.style.width = `${row.getBoundingClientRect().width}px`;
  body.appendChild(clone);
  table.appendChild(body);
  document.body.appendChild(table);
  return table;
}

function stripElementIds(root) {
  root.removeAttribute?.("id");
  root.querySelectorAll?.("[id]").forEach((element) => element.removeAttribute("id"));
  return root;
}

function roomRenameKeyTriggered(key) {
  return key === "Enter" || key === " ";
}

function updateDropPlaceholder(placeholder, targetRow) {
  if (!targetRow || targetRow.classList.contains("room-drag-placeholder")) return;
  const separator = targetRow.classList.contains("room-separator")
    ? targetRow
    : separatorForRow(targetRow);
  if (!separator) return;
  const beforeRow = sortedRoomPosition(separator, placeholder);
  animatePlaceholderMove(placeholder, beforeRow, separator.parentElement);
  clearDropTargets();
  separator.classList.add("room-drop-target");
}

async function saveSensorMove(row, targetSeparator, beforeRow = null) {
  if (!row || !targetSeparator) return false;
  const oldSeparator = separatorForRow(row);
  if (oldSeparator === targetSeparator) return false;
  const oldNext = row.nextElementSibling;
  const request = deviceRoomRequest(row.dataset.deviceId, targetSeparator.dataset.roomId);
  if (beforeRow?.parentElement === targetSeparator.parentElement) {
    targetSeparator.parentElement.insertBefore(row, beforeRow);
    row.dataset.roomId = targetSeparator.dataset.roomId || "";
  } else {
    insertRowInRoom(row, targetSeparator);
  }
  try {
    await persistSensorRoom(row.dataset.deviceId, targetSeparator.dataset.roomId);
    showRoomMatrixMessage(`Moved sensor to ${targetSeparator.dataset.roomName}.`);
    window.dispatchEvent(new CustomEvent("roomassignmentchange", { detail: request }));
    return true;
  } catch (error) {
    restoreSensorPosition(row, oldSeparator, oldNext);
    showRoomMatrixMessage(error.message || "Unable to move sensor.", true);
    return false;
  }
}

function roomBlock(separator) {
  const rows = [separator];
  let row = separator.nextElementSibling;
  while (row && !row.classList.contains("room-separator")) {
    rows.push(row);
    row = row.nextElementSibling;
  }
  return rows;
}

function sortRoomGroups() {
  const tbody = document.querySelector("#room-matrix tbody");
  if (!tbody) return;
  const separators = [...tbody.querySelectorAll(":scope > .room-separator")];
  separators.sort((left, right) =>
    roomNameSortKey(left.dataset.roomName).localeCompare(
      roomNameSortKey(right.dataset.roomName),
    ),
  );
  const fragment = document.createDocumentFragment();
  separators.forEach((separator) => {
    roomBlock(separator).forEach((row) => fragment.appendChild(row));
  });
  tbody.appendChild(fragment);
}

function applyMatrixRoomName(roomId, roomName) {
  const separator = document.querySelector(
    `.room-separator[data-room-id="${roomId}"]`,
  );
  const button = separator?.querySelector(".room-name");
  if (!separator || !button) return;
  separator.dataset.roomName = roomName;
  button.dataset.roomName = roomName;
  button.textContent = roomDisplayName(roomName, separator.dataset.hasFcu);
  button.setAttribute("aria-label", `Manage room ${roomName}`);
  sortRoomGroups();
}

function applyRoomMetrics(roomId, temp10x, humidity) {
  const temp = document.getElementById(`room-summary-temp-${roomId}`);
  const tempC = roomTemperatureC(temp10x);
  if (temp) {
    if (tempC === null) {
      temp.removeAttribute("data-temp-c");
      temp.textContent = "--";
    } else {
      temp.dataset.tempC = String(tempC);
      temp.textContent = TemperatureUtils.formatTemperature(tempC);
    }
  }
  const humidityElement = document.getElementById(
    `room-summary-humidity-${roomId}`,
  );
  if (humidityElement) humidityElement.textContent = roomHumidityText(humidity);
}

function closeRoomRenameDialog() {
  const dialog = document.getElementById("room-rename-dialog");
  if (!dialog) return;
  setRoomRenameSaving(dialog, false);
  dialog.classList.add("hidden");
}

function roomRenameIsSaving(dialog) {
  return dialog?.dataset.saving === "true";
}

function setRoomRenameSaving(dialog, saving) {
  if (!dialog) return;
  if (saving) {
    dialog.dataset.saving = "true";
    dialog.setAttribute("aria-busy", "true");
  } else {
    delete dialog.dataset.saving;
    dialog.removeAttribute("aria-busy");
  }
  dialog.querySelectorAll("input, button").forEach((control) => {
    control.disabled = saving;
  });
}

function cancelRoomRenameDialog() {
  const dialog = document.getElementById("room-rename-dialog");
  if (!dialog || roomRenameIsSaving(dialog)) return false;
  closeRoomRenameDialog();
  return true;
}

function openRoomRenameDialog(button) {
  if (!button || !button.dataset.roomId) return;
  const dialog = document.getElementById("room-rename-dialog");
  const input = document.getElementById("room-rename-name");
  if (!dialog || !input) return;
  dialog.dataset.roomId = button.dataset.roomId;
  dialog.dataset.roomName = button.dataset.roomName || button.textContent.trim();
  setRoomRenameSaving(dialog, false);
  input.value = button.dataset.roomName || button.textContent.trim();
  dialog.querySelector("[data-role='message']").textContent = "";
  dialog
    .querySelector("[data-action='request-room-delete']")
    ?.classList.toggle(
      "hidden",
      button.closest(".room-separator")?.dataset.canDelete !== "true",
    );
  dialog.classList.remove("hidden");
  input.focus();
  input.select();
}

async function renameRoom(dialog) {
  if (roomRenameIsSaving(dialog)) return false;
  const roomId = roomIdFromValue(dialog.dataset.roomId);
  const input = document.getElementById("room-rename-name");
  const message = dialog.querySelector("[data-role='message']");
  const roomName = String(input?.value || "").trim();
  if (roomId === null || !roomName) {
    message.textContent = "Room name is required.";
    return false;
  }
  setRoomRenameSaving(dialog, true);
  message.textContent = "Saving…";
  let data;
  try {
    data = await persistRoomName(roomId, roomName);
  } catch (error) {
    message.textContent = error.message || "Unable to rename room.";
    setRoomRenameSaving(dialog, false);
    input?.focus();
    return false;
  }

  const savedRoomName = data.room_name || roomName;
  let presentationFailed = false;
  try {
    applyMatrixRoomName(roomId, savedRoomName);
    document
      .querySelectorAll(`.fcu-temp-sources-trigger[data-room-id="${roomId}"]`)
      .forEach((trigger) => {
        trigger.dataset.roomName = savedRoomName;
      });
  } catch (error) {
    presentationFailed = true;
    console.error("Room rename was saved, but the page update failed:", error);
  }
  closeRoomRenameDialog();
  if (presentationFailed) {
    if (typeof window !== "undefined") window.location.reload();
    return true;
  }
  try {
    showRoomMatrixMessage(`Renamed room to ${savedRoomName}.`);
  } catch (error) {
    console.error("Room rename was saved, but the confirmation failed:", error);
  }
  return true;
}

function closeRoomCreateDialog() {
  document.getElementById("room-create-dialog")?.classList.add("hidden");
}

function openRoomCreateDialog() {
  const dialog = document.getElementById("room-create-dialog");
  const input = document.getElementById("room-create-name");
  if (!dialog || !input) return;
  input.value = "";
  dialog.querySelector("[data-role='message']").textContent = "";
  dialog.classList.remove("hidden");
  input.focus();
}

async function createRoom(dialog) {
  const input = document.getElementById("room-create-name");
  const message = dialog.querySelector("[data-role='message']");
  const roomName = String(input?.value || "").trim();
  if (!roomName) {
    message.textContent = "Room name is required.";
    return;
  }
  try {
    await persistNewRoom(roomName);
    window.location.reload();
  } catch (error) {
    message.textContent = error.message || "Unable to create room.";
  }
}

function closeRoomDeleteDialog() {
  const dialog = document.getElementById("room-delete-dialog");
  if (!dialog) return;
  clearInterval(dialog._countdownTimer);
  dialog._countdownTimer = null;
  dialog.classList.add("hidden");
}

function openRoomDeleteDialog(roomId, roomName) {
  const dialog = document.getElementById("room-delete-dialog");
  const button = dialog?.querySelector("[data-action='confirm-room-delete']");
  if (!dialog || !button) return;
  clearInterval(dialog._countdownTimer);
  dialog._countdownTimer = null;
  dialog.dataset.roomId = String(roomId);
  dialog.querySelector("[data-role='room-name']").textContent = roomName;
  dialog.querySelector("[data-role='message']").textContent = "";
  dialog.classList.remove("hidden");
  const startedAt = Date.now();
  const update = () => {
    const state = roomDeleteCountdown(startedAt);
    button.disabled = !state.enabled;
    button.textContent = state.label;
    if (state.enabled) {
      clearInterval(dialog._countdownTimer);
      dialog._countdownTimer = null;
    }
  };
  update();
  dialog._countdownTimer = setInterval(update, 250);
}

async function deleteRoom(dialog) {
  const roomId = roomIdFromValue(dialog.dataset.roomId);
  const message = dialog.querySelector("[data-role='message']");
  if (roomId === null) return;
  try {
    await persistRoomDeletion(roomId);
    window.location.reload();
  } catch (error) {
    message.textContent = error.message || "Unable to delete room.";
  }
}

function setupRoomRename() {
  document.querySelectorAll(".room-name:not(.room-name-unassigned)").forEach((button) => {
    button.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      openRoomRenameDialog(button);
    });
    button.addEventListener("keydown", (event) => {
      if (!roomRenameKeyTriggered(event.key)) return;
      event.preventDefault();
      openRoomRenameDialog(button);
    });
    let press = null;
    button.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "touch") return;
      press = { x: event.clientX, y: event.clientY, started: Date.now() };
      press.timer = setTimeout(() => {
        if (press && longPressTriggered(Date.now() - press.started, 0)) {
          openRoomRenameDialog(button);
          press = null;
        }
      }, ROOM_LONG_PRESS_MS);
    });
    button.addEventListener("pointermove", (event) => {
      if (!press) return;
      const movement = Math.hypot(event.clientX - press.x, event.clientY - press.y);
      if (movement > ROOM_POINTER_SLOP_PX) {
        clearTimeout(press.timer);
        press = null;
      }
    });
    ["pointerup", "pointercancel"].forEach((name) =>
      button.addEventListener(name, () => {
        if (press) clearTimeout(press.timer);
        press = null;
      }),
    );
  });
  const dialog = document.getElementById("room-rename-dialog");
  dialog?.querySelector("form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    renameRoom(dialog);
  });
  dialog?.querySelector("[data-action='cancel-room-rename']")?.addEventListener(
    "click",
    cancelRoomRenameDialog,
  );
  dialog?.querySelector("[data-action='request-room-delete']")?.addEventListener(
    "click",
    () => {
      const roomId = roomIdFromValue(dialog.dataset.roomId);
      if (roomId === null) return;
      closeRoomRenameDialog();
      openRoomDeleteDialog(roomId, dialog.dataset.roomName);
    },
  );

  const createDialog = document.getElementById("room-create-dialog");
  document.getElementById("new-room-button")?.addEventListener(
    "click",
    openRoomCreateDialog,
  );
  createDialog?.querySelector("form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    createRoom(createDialog);
  });
  createDialog
    ?.querySelector("[data-action='cancel-room-create']")
    ?.addEventListener("click", closeRoomCreateDialog);

  const deleteDialog = document.getElementById("room-delete-dialog");
  deleteDialog
    ?.querySelector("[data-action='confirm-room-delete']")
    ?.addEventListener("click", () => deleteRoom(deleteDialog));
  deleteDialog
    ?.querySelector("[data-action='cancel-room-delete']")
    ?.addEventListener("click", closeRoomDeleteDialog);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") cancelRoomRenameDialog();
  });
}

function setupRoomDragging() {
  let draggedRow = null;
  let placeholder = null;

  function beginDrag(row) {
    draggedRow = row;
    placeholder = createDragPlaceholder(row);
    row.classList.add("room-dragging", "room-dragging-lifted");
    row.querySelector(".room-drag-handle")?.setAttribute("aria-grabbed", "true");
  }

  function finishDrag(row, saveMove = true) {
    const targetSeparator = placeholder ? separatorForRow(placeholder) : null;
    const beforeRow = placeholder?.nextElementSibling || null;
    placeholder?.remove();
    placeholder = null;
    row.classList.remove("room-dragging", "room-dragging-lifted");
    row.querySelector(".room-drag-handle")?.setAttribute("aria-grabbed", "false");
    clearDropTargets();
    draggedRow = null;
    if (saveMove && targetSeparator) saveSensorMove(row, targetSeparator, beforeRow);
  }

  document.querySelectorAll(".room-sensor-row").forEach((row) => {
    const handle = row.querySelector(".room-drag-handle");
    if (!handle) return;
    let pointerDrag = null;

    function movePointerDrag(event) {
      if (!pointerDrag) return;
      if (Math.hypot(event.clientX - pointerDrag.x, event.clientY - pointerDrag.y) < ROOM_POINTER_SLOP_PX) return;
      event.preventDefault();
      if (!pointerDrag.image) {
        pointerDrag.image = createRowDragImage(row);
        beginDrag(row);
      }
      pointerDrag.image.style.left = `${event.clientX + 12}px`;
      pointerDrag.image.style.top = `${event.clientY + 12}px`;
      const hit = document.elementFromPoint(event.clientX, event.clientY)?.closest("tr");
      updateDropPlaceholder(placeholder, hit);
    }

    function stopPointerDrag(saveMove) {
      const moved = Boolean(pointerDrag?.image);
      pointerDrag?.image?.remove();
      pointerDrag = null;
      window.removeEventListener("pointermove", movePointerDrag);
      window.removeEventListener("pointerup", pointerUp);
      window.removeEventListener("pointercancel", pointerCancel);
      if (moved) finishDrag(row, saveMove);
    }

    function pointerUp() {
      stopPointerDrag(true);
    }

    function pointerCancel() {
      stopPointerDrag(false);
    }

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      pointerDrag = { x: event.clientX, y: event.clientY, image: null };
      window.addEventListener("pointermove", movePointerDrag, { passive: false });
      window.addEventListener("pointerup", pointerUp);
      window.addEventListener("pointercancel", pointerCancel);
    });
  });
}

function setupRoomMatrix() {
  if (!document.getElementById("room-matrix")) return;
  setupRoomDragging();
  setupRoomRename();
}

if (typeof window !== "undefined") {
  window.addEventListener("DOMContentLoaded", setupRoomMatrix);
  window.addEventListener("roommetricschange", (event) => {
    applyRoomMetrics(
      event.detail.roomId,
      event.detail.calculatedTemp10x,
      event.detail.calculatedHumidity,
    );
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    compareSensors,
    cancelRoomRenameDialog,
    deviceRoomRequest,
    longPressTriggered,
    openRoomDeleteDialog,
    persistNewRoom,
    persistRoomDeletion,
    persistRoomName,
    persistSensorRoom,
    restoreSensorPosition,
    renameRoom,
    roomRenameIsSaving,
    roomRenameKeyTriggered,
    roomHumidityText,
    roomDeleteCountdown,
    roomDisplayName,
    roomIdFromValue,
    roomNameSortKey,
    roomTemperatureC,
    stripElementIds,
  };
}
