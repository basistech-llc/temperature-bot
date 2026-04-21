// clickable_cells.js
// Turn any element with a `data-chart-url` attribute into a link: clicking it
// navigates to the URL. Used by table cells on / and /air-quality to open a
// per-device chart without requiring each page to re-wire the handler.

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-chart-url]").forEach(function (cell) {
    cell.addEventListener("click", function () {
      window.location.href = cell.dataset.chartUrl;
    });
  });
});
