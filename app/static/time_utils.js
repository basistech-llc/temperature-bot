// Time utility functions for formatting and displaying time-related values
// [TODO] Move more time-related utility functions here soon (e.g., formatTimestamp, etc.)

// Format time duration from seconds to human-readable string
function formatDuration(seconds) {
  if (seconds === null) return 'Active';

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  const parts = [];
  if (days > 0) {
    parts.push(days + 'd');
  }
  if (days > 0 || hours > 0) {
    parts.push(hours + 'h');
  }
  parts.push(minutes + 'm');

  return parts.join(' ');
}

// Export for Node.js testing if in Node environment
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { formatDuration };
}

