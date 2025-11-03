/**
 * Simple Node.js tests for time utility functions
 * Run with: node tests/test_time_utils.js
 */
const { formatDuration } = require('../app/static/time_utils.js');

// Test cases: [seconds, expected_format]
const testCases = [
    [null, "Active"],  // null should return "Active"
    [0, "0m"],  // 0 seconds = 0 minutes
    [30, "0m"],  // 30 seconds = 0 minutes (rounded down)
    [60, "1m"],  // 1 minute
    [90, "1m"],  // 1.5 minutes = 1 minute (rounded down)
    [3599, "59m"],  // 59 minutes 59 seconds = 59 minutes
    [3600, "1h 0m"],  // 1 hour = 1h 0m
    [3660, "1h 1m"],  // 1 hour 1 minute = 1h 1m
    [7200, "2h 0m"],  // 2 hours = 2h 0m
    [9000, "2h 30m"],  // 2.5 hours = 2h 30m
    [86400, "1d 0h 0m"],  // 1 day = 1d 0h 0m
    [864480, "10d 0h 8m"],  // 10 days 8 minutes = 10d 0h 8m (user's example)
    [90000, "1d 1h 0m"],  // 1 day 1 hour = 1d 1h 0m
    [893280, "10d 8h 8m"],  // 10 days 8 hours 8 minutes (248h 8m in old format)
    [172800, "2d 0h 0m"],  // 2 days = 2d 0h 0m
    [259200, "3d 0h 0m"],  // 3 days = 3d 0h 0m
    [604800, "7d 0h 0m"],  // 7 days = 7d 0h 0m
    [691200, "8d 0h 0m"],  // 8 days = 8d 0h 0m
    [259380, "3d 0h 3m"],  // 3 days 3 minutes = 3d 0h 3m
    [43200, "12h 0m"],  // 12 hours = 12h 0m (no days)
];

let passed = 0;
let failed = 0;

console.log('Testing formatDuration function...\n');

testCases.forEach(([seconds, expected]) => {
    const result = formatDuration(seconds);
    if (result === expected) {
        passed++;
        console.log(`✓ formatDuration(${seconds === null ? 'null' : seconds}) = "${result}"`);
    } else {
        failed++;
        console.error(`✗ formatDuration(${seconds === null ? 'null' : seconds}) = "${result}", expected "${expected}"`);
    }
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);

