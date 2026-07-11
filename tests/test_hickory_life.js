/**
 * Node.js tests for the Hickory Game of Life easter egg logic.
 * Run with: node tests/test_hickory_life.js
 */
const {
  advanceLifeSimulation,
  aliveCount,
  cornerForPoint,
  createCornerSequenceRecognizer,
  createRepeatedCornerRecognizer,
  makeLifeSimulation,
  nextLifeGrid,
  showReloadOverlay,
} = require("../app/static/hickory_life.js");

let passed = 0;
let failed = 0;

function check(label, actual, expected) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson === expectedJson) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}: got ${actualJson}, expected ${expectedJson}`);
  }
}

function checkTrue(label, condition) {
  if (condition) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL ${label}`);
  }
}

const lonelyCell = [
  [0, 0, 0],
  [0, 1, 0],
  [0, 0, 0],
];
check("lonely cell dies", nextLifeGrid(lonelyCell, false), [
  [0, 0, 0],
  [0, 0, 0],
  [0, 0, 0],
]);
check("empty wrapped grid stays empty", nextLifeGrid([], true), []);

const block = [
  [0, 0, 0, 0],
  [0, 1, 1, 0],
  [0, 1, 1, 0],
  [0, 0, 0, 0],
];
check("block remains stable", nextLifeGrid(block, false), block);
const blockStep = advanceLifeSimulation(makeLifeSimulation(block), false);
check("stable block requests reset", blockStep.resetReason, "stable");

const verticalBlinker = [
  [0, 1, 0],
  [0, 1, 0],
  [0, 1, 0],
];
const horizontalBlinker = [
  [0, 0, 0],
  [1, 1, 1],
  [0, 0, 0],
];
check("blinker first phase", nextLifeGrid(verticalBlinker, false), horizontalBlinker);
let blinkerSim = makeLifeSimulation(verticalBlinker);
let blinkerStep = advanceLifeSimulation(blinkerSim, false);
check("first blinker step is not reset", blinkerStep.resetReason, "");
blinkerStep = advanceLifeSimulation(blinkerStep.simulation, false);
check("second blinker step detects cycle", blinkerStep.resetReason, "cycle");

check("aliveCount counts live cells", aliveCount(horizontalBlinker), 3);

check("top-left corner", cornerForPoint(5, 5, 1000, 800, 72), "top-left");
check("top-right corner", cornerForPoint(995, 5, 1000, 800, 72), "top-right");
check("bottom-left corner", cornerForPoint(5, 795, 1000, 800, 72), "bottom-left");
check("bottom-right corner", cornerForPoint(995, 795, 1000, 800, 72), "bottom-right");
check("center is not a corner", cornerForPoint(500, 400, 1000, 800, 72), null);

let completed = 0;
const recognizer = createCornerSequenceRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  timeoutMs: 500,
  onComplete: () => {
    completed += 1;
  },
});
checkTrue("sequence starts at top-left", recognizer.handlePoint(5, 5, 0).matched);
checkTrue("sequence accepts top-right", recognizer.handlePoint(995, 5, 100).matched);
checkTrue("sequence accepts bottom-left", recognizer.handlePoint(5, 795, 200).matched);
const finalCorner = recognizer.handlePoint(995, 795, 300);
checkTrue("sequence accepts bottom-right", finalCorner.matched);
check("sequence completes once", completed, 1);

const timeoutRecognizer = createCornerSequenceRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  timeoutMs: 50,
  onComplete: () => {
    completed += 1;
  },
});
checkTrue("timeout recognizer starts", timeoutRecognizer.handlePoint(5, 5, 0).matched);
check("timeout resets before top-right", timeoutRecognizer.handlePoint(995, 5, 100).matched, false);

const wrongOrder = createCornerSequenceRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  timeoutMs: 500,
  onComplete: () => {
    completed += 1;
  },
});
checkTrue("wrong-order recognizer starts", wrongOrder.handlePoint(5, 5, 0).matched);
check("wrong-order recognizer rejects bottom-right", wrongOrder.handlePoint(995, 795, 100).matched, false);

let defaultCompleted = 0;
const defaultRecognizer = createCornerSequenceRecognizer({
  width: 1000,
  height: 800,
  onComplete: () => {
    defaultCompleted += 1;
  },
});
checkTrue("default hit area includes 100px top-left", defaultRecognizer.handlePoint(100, 100, 0).matched);
checkTrue("default timeout allows deliberate top-right", defaultRecognizer.handlePoint(900, 100, 3000).matched);
checkTrue("default timeout allows deliberate bottom-left", defaultRecognizer.handlePoint(100, 700, 6000).matched);
checkTrue("default timeout allows deliberate bottom-right", defaultRecognizer.handlePoint(900, 700, 9000).matched);
check("default sequence completes", defaultCompleted, 1);

let reloadCorner = "";
const reloadRecognizer = createRepeatedCornerRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  neededClicks: 4,
  windowMs: 4000,
  onComplete: corner => {
    reloadCorner = corner;
  },
});
check("reload recognizer first click", reloadRecognizer.handlePoint(5, 5, 0), {
  corner: "top-left",
  matched: true,
  completed: false,
  count: 1,
});
check("reload recognizer second click", reloadRecognizer.handlePoint(6, 6, 1000).count, 2);
check("reload recognizer third click", reloadRecognizer.handlePoint(7, 7, 2000).count, 3);
check("reload recognizer fourth click completes", reloadRecognizer.handlePoint(8, 8, 4000), {
  corner: "top-left",
  matched: true,
  completed: true,
  count: 4,
});
check("reload recognizer reports completed corner", reloadCorner, "top-left");

let reloadCompletions = 0;
const slowReloadRecognizer = createRepeatedCornerRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  neededClicks: 4,
  windowMs: 4000,
  onComplete: () => {
    reloadCompletions += 1;
  },
});
slowReloadRecognizer.handlePoint(995, 795, 0);
slowReloadRecognizer.handlePoint(995, 795, 1000);
slowReloadRecognizer.handlePoint(995, 795, 2000);
check("reload recognizer resets after window", slowReloadRecognizer.handlePoint(995, 795, 4001), {
  corner: "bottom-right",
  matched: true,
  completed: false,
  count: 1,
});
check("slow reload sequence does not complete", reloadCompletions, 0);

const changingCornerReload = createRepeatedCornerRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  neededClicks: 4,
  windowMs: 4000,
  onComplete: () => {
    reloadCompletions += 1;
  },
});
changingCornerReload.handlePoint(5, 5, 0);
changingCornerReload.handlePoint(995, 5, 500);
changingCornerReload.handlePoint(5, 795, 1000);
const changingCornerFinal = changingCornerReload.handlePoint(995, 795, 1500);
check("four different corners do not reload", changingCornerFinal.completed, false);
check("changing corners keep latest count at one", changingCornerFinal.count, 1);

const interruptedReload = createRepeatedCornerRecognizer({
  width: 1000,
  height: 800,
  hitSize: 72,
  neededClicks: 4,
  windowMs: 4000,
  onComplete: () => {
    reloadCompletions += 1;
  },
});
interruptedReload.handlePoint(5, 5, 0);
interruptedReload.handlePoint(5, 5, 1000);
check("non-corner resets reload recognizer", interruptedReload.handlePoint(500, 400, 1500), {
  corner: null,
  matched: false,
  completed: false,
  count: 0,
});
check("interrupted reload sequence starts again", interruptedReload.handlePoint(5, 5, 2000).count, 1);

function fakeDocument() {
  function makeElement(tagName) {
    return {
      tagName,
      attributes: {},
      children: [],
      className: "",
      id: "",
      textContent: "",
      appendChild(child) {
        child.parent = this;
        this.children.push(child);
        return child;
      },
      remove() {
        if (!this.parent) return;
        this.parent.children = this.parent.children.filter(child => child !== this);
      },
      setAttribute(name, value) {
        this.attributes[name] = value;
      },
    };
  }

  return {
    body: makeElement("body"),
    head: makeElement("head"),
    createElement: makeElement,
    getElementById: () => null,
  };
}

const originalDocument = global.document;
const originalWindow = global.window;
const originalSetTimeout = global.setTimeout;
try {
  const timers = [];
  const document = fakeDocument();
  let reloads = 0;
  global.document = document;
  global.window = {
    location: {
      reload: () => {
        reloads += 1;
      },
    },
  };
  global.setTimeout = (callback, delayMs) => {
    timers.push({ callback, delayMs });
    return timers.length;
  };

  showReloadOverlay();
  check("reload flash appends one overlay", document.body.children.length, 1);
  check(
    "reload flash overlay class",
    document.body.children[0].className,
    "hickory-life-overlay hickory-life-reload-overlay",
  );
  check("reload flash message text", document.body.children[0].children[0].textContent, "reloading");
  check("reload flash delay", timers[0].delayMs, 250);
  check("reload is not immediate", reloads, 0);
  timers[0].callback();
  check("reload happens after flash", reloads, 1);
} finally {
  global.document = originalDocument;
  global.window = originalWindow;
  global.setTimeout = originalSetTimeout;
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
