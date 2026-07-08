/**
 * Node.js tests for the Hickory Game of Life easter egg logic.
 * Run with: node tests/test_hickory_life.js
 */
const {
  advanceLifeSimulation,
  aliveCount,
  cornerForPoint,
  createCornerSequenceRecognizer,
  makeLifeSimulation,
  nextLifeGrid,
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

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
