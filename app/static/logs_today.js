// Log table functionality for Activity Log page

const LOG_PAGE_SIZE = 50;

let logTable;
let logRows = [];
let newestLogtime = null;
let allHistoryLoaded = false;

function updateRangeSummary() {
  const summary = document.getElementById("log-range-summary");
  if (!summary) return;
  const count = logRows.length;
  if (count === 0) {
    summary.textContent = "No log entries loaded.";
    return;
  }
  summary.textContent = `Showing latest ${count} entr${count === 1 ? "y" : "ies"}.`;
}

function applyLogRowsToTable() {
  if (!logTable) return;
  logTable.setData(logRows);
  updateRangeSummary();
}

async function fetchLogs({ startTs, endTs, length, startRow }) {
  const params = new URLSearchParams();
  if (typeof startTs === "number") {
    params.set("start", String(startTs));
  }
  if (typeof endTs === "number") {
    params.set("end", String(endTs));
  }
  if (typeof length === "number") {
    params.set("length", String(length));
  }
  if (typeof startRow === "number") {
    params.set("start_row", String(startRow));
  }
  const url = `/api/v1/logs?${params.toString()}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Failed to fetch logs: ${resp.status}`);
  }
  const json = await resp.json();
  return Array.isArray(json.data) ? json.data : [];
}

function createLogTable() {
  logTable = new Tabulator("#log-table", {
    layout: "fitColumns",
    data: [],
    columns: [
      {
        title: "Time",
        field: "logtime",
        sorter: "number",
        width: 180,
        formatter: function (cell) {
          const ts = cell.getValue() * 1000;
          return new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZoneName: "short",
          }).format(new Date(ts));
        },
        widthGrow: 2,
      },
      { title: "IP Address", field: "ipaddr", width: 130 },
      { title: "Unit", field: "unit", hozAlign: "left", minWidth: 260, widthGrow: 3 },
      { title: "Speed", field: "new_value", hozAlign: "center" },
      { title: "Agent", field: "agent", widthGrow: 1 },
      { title: "Comment", field: "comment", widthGrow: 3 },
    ],
    placeholder: "No logs found.",
  });
}

async function loadInitialLogs() {
  try {
    const rows = await fetchLogs({ length: LOG_PAGE_SIZE, startRow: 0 });
    logRows = rows.slice();
    if (logRows.length > 0) {
      // rows are newest-first from API
      newestLogtime = logRows[0].logtime;
      if (logRows.length < LOG_PAGE_SIZE) {
        allHistoryLoaded = true;
      }
    } else {
      newestLogtime = null;
      allHistoryLoaded = true;
    }
    applyLogRowsToTable();
    const btn = document.getElementById("log-show-more");
    if (btn) {
      btn.disabled = allHistoryLoaded;
    }
  } catch (e) {
    console.error(e);
  }
}

async function loadOlderLogs() {
  if (allHistoryLoaded) {
    return;
  }
  try {
    const rows = await fetchLogs({
      length: LOG_PAGE_SIZE,
      startRow: logRows.length,
    });
    if (!rows.length) {
      allHistoryLoaded = true;
      const btn = document.getElementById("log-show-more");
      if (btn) {
        btn.disabled = true;
      }
      return;
    }
    logRows = logRows.concat(rows);
    if (rows.length < LOG_PAGE_SIZE) {
      allHistoryLoaded = true;
      const btn = document.getElementById("log-show-more");
      if (btn) {
        btn.disabled = true;
      }
    }
    applyLogRowsToTable();
  } catch (e) {
    console.error(e);
  }
}

function refreshLogTable() {
  if (!logTable || newestLogtime == null) {
    return;
  }
  fetchLogs({ startTs: newestLogtime + 1, length: LOG_PAGE_SIZE })
    .then((rows) => {
      if (!rows.length) {
        return;
      }
      // Prepend newer rows (API returns newest-first).
      logRows = rows.concat(logRows);
      newestLogtime = logRows[0].logtime;
      applyLogRowsToTable();
    })
    .catch((e) => {
      console.error(e);
    });
}

// Auto-refresh the log table every 30 seconds
window.addEventListener("DOMContentLoaded", function () {
  createLogTable();
  loadInitialLogs();

  const showMoreButton = document.getElementById("log-show-more");
  if (showMoreButton) {
    showMoreButton.addEventListener("click", function () {
      loadOlderLogs();
    });
  }

  setInterval(refreshLogTable, 30000); // Refresh every 30 seconds
});
