// Log table functionality for Today's Log page

const LOG_DAYS = 5;
const SECONDS_PER_DAY = 60 * 60 * 24;

function getTodayUnixRange() {
  const now = new Date();
  const start_today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );
  const start = new Date(
    start_today.getTime() - (LOG_DAYS - 1) * SECONDS_PER_DAY * 1000,
  );
  const end = new Date(start_today.getTime() + 86400000); // midnight next day
  return {
    start: Math.floor(start.getTime() / 1000),
    end: Math.floor(end.getTime() / 1000),
  };
}

let logTable;
function createLogTable() {
  const { start, end } = getTodayUnixRange();
  console.log("start=", start, "end=", end);

  logTable = new Tabulator("#log-table", {
    layout: "fitColumns",
    height: "400px",
    ajaxURL: `/api/v1/logs?start=${start}&end=${end}`,
    ajaxResponse: function (url, params, response) {
      return response.data; // Tabulator expects an array of row objects
    },
    columns: [
      {
        title: "Time",
        field: "logtime",
        sorter: "number",
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
      { title: "IP Address", field: "ipaddr", widthGrow: 2 },
      { title: "Unit", field: "unit", hozAlign: "center" },
      { title: "Speed", field: "new_value", hozAlign: "center" },
      { title: "Agent", field: "agent", widthGrow: 2 },
      { title: "Comment", field: "comment", widthGrow: 3 },
    ],
    placeholder: "No logs found for today.",
    pagination: "local",
    paginationSize: 10,
  });
}

function refreshLogTable() {
  const { start, end } = getTodayUnixRange();
  logTable.setData(`/api/v1/logs?start=${start}&end=${end}`);
}

// Auto-refresh the log table every 30 seconds
window.addEventListener("DOMContentLoaded", function () {
  createLogTable();
  setInterval(refreshLogTable, 30000); // Refresh every 30 seconds
});

