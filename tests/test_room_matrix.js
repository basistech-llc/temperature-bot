"use strict";

const assert = require("assert");
const {
  cancelRoomRenameDialog,
  compareSensors,
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
  roomHumidityText,
  roomDeleteCountdown,
  roomDisplayName,
  roomIdFromValue,
  roomNameSortKey,
  roomRenameKeyTriggered,
  roomTemperatureC,
  stripElementIds,
} = require("../app/static/room_matrix.js");

assert.strictEqual(roomIdFromValue(""), null);
assert.strictEqual(roomIdFromValue(null), null);
assert.strictEqual(roomIdFromValue("17"), 17);
assert.strictEqual(roomIdFromValue("not-a-room"), null);

assert.deepStrictEqual(deviceRoomRequest("42", "7"), {
  device_id: 42,
  room_id: 7,
});
assert.deepStrictEqual(deviceRoomRequest(42, ""), {
  device_id: 42,
  room_id: null,
});

assert.strictEqual(longPressTriggered(649, 0), false);
assert.strictEqual(longPressTriggered(650, 10), true);
assert.strictEqual(longPressTriggered(800, 11), false);
assert.strictEqual(roomRenameKeyTriggered("Enter"), true);
assert.strictEqual(roomRenameKeyTriggered(" "), true);
assert.strictEqual(roomRenameKeyTriggered("Escape"), false);
assert.strictEqual(roomDisplayName("Broadway North", true), "Broadway North 🌀");
assert.strictEqual(roomDisplayName("Conference", false), "Conference");
assert.deepStrictEqual(roomDeleteCountdown(1000, 1000), {
  enabled: false,
  label: "OK (5)",
});
assert.deepStrictEqual(roomDeleteCountdown(1000, 5999), {
  enabled: false,
  label: "OK (1)",
});
assert.deepStrictEqual(roomDeleteCountdown(1000, 6000), {
  enabled: true,
  label: "OK",
});

const originalDocument = global.document;
const originalSetInterval = global.setInterval;
const originalClearInterval = global.clearInterval;
const clearedTimers = [];
let nextTimer = 100;
const deleteButton = {};
const deleteRoomName = {};
const deleteMessage = {};
const deleteDialog = {
  dataset: {},
  classList: { remove() {} },
  querySelector(selector) {
    return {
      "[data-action='confirm-room-delete']": deleteButton,
      "[data-role='room-name']": deleteRoomName,
      "[data-role='message']": deleteMessage,
    }[selector];
  },
};
global.document = { getElementById: () => deleteDialog };
global.setInterval = () => ++nextTimer;
global.clearInterval = (timer) => {
  if (timer !== undefined && timer !== null) clearedTimers.push(timer);
};
openRoomDeleteDialog(7, "First room");
const firstTimer = deleteDialog._countdownTimer;
openRoomDeleteDialog(8, "Second room");
assert.deepStrictEqual(clearedTimers, [firstTimer]);
assert.strictEqual(deleteDialog.dataset.roomId, "8");
assert.notStrictEqual(deleteDialog._countdownTimer, firstTimer);
global.document = originalDocument;
global.setInterval = originalSetInterval;
global.clearInterval = originalClearInterval;

const dragCloneChildren = [
  { id: "temp-1", removeAttribute: (name) => { if (name === "id") delete dragCloneChildren[0].id; } },
  { id: "notes-1", removeAttribute: (name) => { if (name === "id") delete dragCloneChildren[1].id; } },
];
const dragClone = {
  id: "row-1",
  removeAttribute(name) { if (name === "id") delete this.id; },
  querySelectorAll: () => dragCloneChildren,
};
stripElementIds(dragClone);
assert.strictEqual(dragClone.id, undefined);
assert.deepStrictEqual(dragCloneChildren.map((child) => child.id), [undefined, undefined]);

assert.strictEqual(roomTemperatureC(215), 21.5);
assert.strictEqual(roomTemperatureC(null), null);
assert.strictEqual(roomTemperatureC(undefined), null);
assert.strictEqual(roomHumidityText(42.6), "43%");
assert.strictEqual(roomHumidityText(undefined), "--");
assert.strictEqual(roomHumidityText(null), "--");

assert.ok(compareSensors("Alpha", 8, "Bravo", 2) < 0);
assert.ok(compareSensors("bravo", 8, "Bravo", 12) < 0);
assert.ok(compareSensors("Charlie", 1, "Bravo", 12) > 0);

assert.deepStrictEqual(
  ["Unassigned", "bamboo", "Area 51"].sort((left, right) =>
    roomNameSortKey(left).localeCompare(roomNameSortKey(right)),
  ),
  ["Area 51", "bamboo", "Unassigned"],
);

async function testPersistenceTransitions() {
  const requests = [];
  const successfulRequest = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ room_name: "Bravo" }) };
  };
  await persistSensorRoom(42, 7, successfulRequest);
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0].url, "/api/v1/update_device_room");
  assert.deepStrictEqual(JSON.parse(requests[0].options.body), {
    device_id: 42,
    room_id: 7,
  });

  const renamed = await persistRoomName(7, "Bravo", successfulRequest);
  assert.strictEqual(renamed.room_name, "Bravo");
  assert.strictEqual(requests[1].url, "/api/v1/rooms/7");
  assert.deepStrictEqual(JSON.parse(requests[1].options.body), {
    room_name: "Bravo",
  });

  const created = await persistNewRoom("Delta", successfulRequest);
  assert.strictEqual(created.room_name, "Bravo");
  assert.strictEqual(requests[2].url, "/api/v1/rooms");
  assert.strictEqual(requests[2].options.method, "POST");
  assert.deepStrictEqual(JSON.parse(requests[2].options.body), {
    room_name: "Delta",
  });

  await persistRoomDeletion(7, successfulRequest);
  assert.strictEqual(requests[3].url, "/api/v1/rooms/7");
  assert.strictEqual(requests[3].options.method, "DELETE");

  await assert.rejects(
    persistRoomName(7, "Alpha", async () => ({
      ok: false,
      json: async () => ({ error: "Room name already exists" }),
    })),
    /Room name already exists/,
  );

  const row = {
    dataset: { roomId: "7" },
    parentElement: {
      insertBefore(movedRow, nextRow) {
        assert.strictEqual(movedRow, row);
        assert.strictEqual(nextRow, originalNextRow);
      },
    },
  };
  const originalSeparator = { dataset: { roomId: "3" } };
  const originalNextRow = {};
  restoreSensorPosition(row, originalSeparator, originalNextRow);
  assert.strictEqual(row.dataset.roomId, "3");
}

function fakeClassList(initial = []) {
  const classes = new Set(initial);
  return {
    add: (...names) => names.forEach((name) => classes.add(name)),
    contains: (name) => classes.has(name),
    remove: (...names) => names.forEach((name) => classes.delete(name)),
  };
}

function fakeRenameDialog(roomName = "Bravo") {
  const controls = [{ disabled: false }, { disabled: false }, { disabled: false }];
  const message = { textContent: "" };
  return {
    attributes: {},
    classList: fakeClassList(),
    controls,
    dataset: { roomId: "7", roomName: "Alpha" },
    input: { focusCount: 0, value: roomName, focus() { this.focusCount++; } },
    message,
    querySelector: (selector) =>
      selector === "[data-role='message']" ? message : null,
    querySelectorAll: () => controls,
    removeAttribute(name) { delete this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
}

async function testRoomRenameCompletion() {
  const originalDocument = global.document;
  const originalFetch = global.fetch;
  const originalWindow = global.window;
  const originalConsoleError = console.error;
  let releaseRequest;
  let requestCount = 0;
  const dialog = fakeRenameDialog();
  const errors = [];
  let reloadCount = 0;
  global.document = {
    getElementById(id) {
      if (id === "room-rename-dialog") return dialog;
      if (id === "room-rename-name") return dialog.input;
      return null;
    },
    querySelector() {
      throw new Error("simulated rendering failure");
    },
  };
  global.fetch = async () => {
    requestCount++;
    await new Promise((resolve) => { releaseRequest = resolve; });
    return { ok: true, json: async () => ({ room_name: "Bravo" }) };
  };
  global.window = { location: { reload: () => { reloadCount++; } } };
  console.error = (...args) => errors.push(args.join(" "));

  try {
    const first = renameRoom(dialog);
    assert.strictEqual(roomRenameIsSaving(dialog), true);
    assert.strictEqual(dialog.attributes["aria-busy"], "true");
    assert.ok(dialog.controls.every((control) => control.disabled));
    assert.strictEqual(dialog.message.textContent, "Saving…");
    assert.strictEqual(cancelRoomRenameDialog(), false);
    assert.strictEqual(await renameRoom(dialog), false);
    assert.strictEqual(requestCount, 1);

    releaseRequest();
    assert.strictEqual(await first, true);
    assert.strictEqual(dialog.classList.contains("hidden"), true);
    assert.strictEqual(roomRenameIsSaving(dialog), false);
    assert.ok(dialog.controls.every((control) => !control.disabled));
    assert.ok(errors.some((message) => message.includes("rename was saved")));
    assert.strictEqual(reloadCount, 1);

    dialog.classList.remove("hidden");
    assert.strictEqual(cancelRoomRenameDialog(), true);
    assert.strictEqual(dialog.classList.contains("hidden"), true);
  } finally {
    global.document = originalDocument;
    global.fetch = originalFetch;
    global.window = originalWindow;
    console.error = originalConsoleError;
  }
}

async function testRoomRenameErrorRecovery() {
  const originalDocument = global.document;
  const originalFetch = global.fetch;
  const dialog = fakeRenameDialog("Duplicate");
  global.document = {
    getElementById(id) {
      if (id === "room-rename-dialog") return dialog;
      if (id === "room-rename-name") return dialog.input;
      return null;
    },
  };
  global.fetch = async () => ({
    ok: false,
    json: async () => ({ error: "Room name already exists" }),
  });

  try {
    assert.strictEqual(await renameRoom(dialog), false);
    assert.strictEqual(dialog.classList.contains("hidden"), false);
    assert.strictEqual(roomRenameIsSaving(dialog), false);
    assert.ok(dialog.controls.every((control) => !control.disabled));
    assert.strictEqual(dialog.input.value, "Duplicate");
    assert.strictEqual(dialog.input.focusCount, 1);
    assert.strictEqual(dialog.message.textContent, "Room name already exists");
  } finally {
    global.document = originalDocument;
    global.fetch = originalFetch;
  }
}

testPersistenceTransitions()
  .then(testRoomRenameCompletion)
  .then(testRoomRenameErrorRecovery)
  .then(() => console.log("room_matrix tests passed"))
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
