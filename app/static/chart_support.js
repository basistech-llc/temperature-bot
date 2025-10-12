// chart_support.js - AQI and Temperature chart functionality

let chart;                      // temperature chart
let rawData = [];               // original data from API
let currentStart = null;
let currentEnd = null;
let currentDeviceIds = null; // for device support (single or multiple)
let allDevices = []; // all available devices for dropdown
const TEMP_ENDPOINT = '/api/v1/temperature';
const AQ_ENDPOINT = '/api/v1/air_quality';


// Air Quality chart setup
// =======================
let aqChart;
let aqRaw = {
    pm25: [], // each: [ts_seconds, value]
    pm10: [],
    o3:   [],
    no2:  [],
    co:   [],
    aqi:  []
};

// Air Quality Units
function unitFor(name) {
    switch (name) {
    case 'PM2.5':
    case 'PM10': return ' µg/m³';
    case 'O₃':
    case 'NO₂':  return ' ppb';
    case 'CO':   return ' ppm';
    default:     return '';
    }
}


// Load data from API with optional parameters
function loadData(deviceIds = null, start = null, end = null) {
    let url = TEMP_ENDPOINT;
    const params = new URLSearchParams();

    // Support single device or multiple devices
    if (deviceIds && deviceIds.length > 0) {
        params.append('device_ids', deviceIds.join(','));
    }
    if (start) params.append('start', start);
    if (end) params.append('end', end);

    if (params.toString()) {
        url += '?' + params.toString();
    }

    fetch(url)
        .then(response => response.json())
        .then(json => {
            rawData = json.series;
            const checkboxContainer = document.getElementById('checkboxes');
            checkboxContainer.innerHTML = '';

            // Only show checkboxes if not filtering by device
            if (!deviceIds) {
                rawData.forEach((series, index) => {
                    const id = `checkbox-${index}`;
                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.id = id;
                    checkbox.checked = true;

                    const label = document.createElement('label');
                    label.htmlFor = id;
                    label.innerText = series.name;

                    checkbox.addEventListener('change', updateChart);
                    checkboxContainer.appendChild(checkbox);
                    checkboxContainer.appendChild(label);
                });
            }

            // Update record count display
            updateRecordCount();
            updateChart();
        });
}



// Temperature chart
document.addEventListener('DOMContentLoaded', function() {
    chart = echarts.init(document.getElementById('main'));
    aqChart = echarts.init(document.getElementById('airquality'));

    // Get device_ids from template variable (will be set by chart.html by jinja2)
    if (typeof window.currentDeviceIds !== 'undefined') {
        currentDeviceIds = window.currentDeviceIds;
    }

    // Initial load
    loadData(currentDeviceIds, currentStart, currentEnd);

    // Load all devices for dropdown
    loadAllDevices();

    // Set up event listeners
    setupEventListeners();
});

// Format time intelligently based on time scale
function formatTime(ts) {
    const date = new Date(ts);
    const now = new Date();

    // Check if we're in day view (last 24 hours)
    const isDayView = currentStart && currentEnd && (currentEnd - currentStart) <= 24 * 60 * 60;

    if (isDayView) {
        // For day view, show only time (HH:mm) since all data is same day
        return new Intl.DateTimeFormat(undefined, {
            hour: '2-digit',
            minute: '2-digit'
        }).format(date);
    } else {
        // For longer periods, show day and time
        return new Intl.DateTimeFormat(undefined, {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        }).format(date);
    }
}

// Update record count display
function updateRecordCount() {
    let totalRecords = 0;
    rawData.forEach(series => {
        totalRecords += series.data.length;
    });

    // Create or update record count element
    let recordCountElement = document.getElementById('record-count');
    if (!recordCountElement) {
        recordCountElement = document.createElement('div');
        recordCountElement.id = 'record-count';

        // Find the controls element
        const controlsElement = document.getElementById('controls');
        if (controlsElement) {
            // Insert at the beginning of controls, before the flex container
            controlsElement.insertBefore(recordCountElement, controlsElement.firstChild);
        }
    }
    recordCountElement.textContent = `Records loaded: ${totalRecords}`;
}


function loadAirQuality(deviceIds = null, start = null, end = null) {
    let url = AQ_ENDPOINT;
    const params = new URLSearchParams();

    if (deviceIds && deviceIds.length > 0) params.append('device_ids', deviceIds.join(','));
    if (start) params.append('start', start);
    if (end)   params.append('end',   end);

    if (params.toString()) url += '?' + params.toString();

    return fetch(url)
        .then(r => r.json())
        .then(json => {
            // Expected shape (example):
            // { pm25: [[ts,val],...], pm10: [...], o3: [...], no2: [...], co: [...], aqi: [...] }
            aqRaw = json;
            updateAQChart();
        })
        .catch(err => {
            console.error('Error loading air quality:', err);
            // Keep previous data if fetch fails
            updateAQChart();
        });
}


function updateChart() {
    const checkboxes = document.querySelectorAll('#checkboxes input[type=checkbox]');
    const series = [];

    // If filtering by device, show all data
    if (currentDeviceIds) {
        rawData.forEach(s => {
            series.push({
                name: s.name,
                type: 'line',
                showSymbol: false,
                data: s.data.map(([ts, val]) => [ts * 1000, val]) // convert to ms
            });
        });
    } else {
        // Show only checked series
        checkboxes.forEach((cb, i) => {
            if (cb.checked) {
                series.push({
                    name: rawData[i].name,
                    type: 'line',
                    showSymbol: false,
                    data: rawData[i].data.map(([ts, val]) => [ts * 1000, val]) // convert to ms
                });
            }
        });
    }

    // --- Add vertical dotted lines for day breaks ---
    // Find min and max timestamps across all series
    let minTs = Infinity;
    let maxTs = -Infinity;
    series.forEach(s => {
        s.data.forEach(([ts, _]) => {
            if (ts < minTs) minTs = ts;
            if (ts > maxTs) maxTs = ts;
        });
    });

    // Generate day boundaries between min and max
    const markLines = [];
    if (minTs !== Infinity && maxTs !== -Infinity) {
        // Get start of first day (midnight)
        const firstDay = new Date(minTs);
        firstDay.setHours(0, 0, 0, 0);
        let currentDay = new Date(firstDay.getTime() + 86400000); // Start with next day

        // Add a line for each day boundary up to max timestamp
        while (currentDay.getTime() <= maxTs) {
            markLines.push({
                xAxis: currentDay.getTime(),
                lineStyle: {
                    type: 'dotted',
                    color: '#bbb',
                    width: 1
                },
                label: { show: false }
            });
            currentDay.setTime(currentDay.getTime() + 86400000); // Add 24 hours
        }
    }
    // --- End vertical lines ---

    const option = {
        title: {
            text: (() => {
                let baseTitle = currentDeviceIds && currentDeviceIds.length > 1 ?
                    `Temperature Time Series - Multiple Devices` :
                    currentDeviceIds && currentDeviceIds.length === 1 ?
                    `Temperature Time Series - Device ${currentDeviceIds[0]}` :
                    'Temperature Time Series';

                // Add date to title for day view
                if (currentStart && currentEnd && (currentEnd - currentStart) <= 24 * 60 * 60) {
                    const dayDate = new Date(currentStart * 1000);
                    const dayStr = new Intl.DateTimeFormat(undefined, {
                        weekday: 'long',
                        month: 'long',
                        day: 'numeric',
                        year: 'numeric'
                    }).format(dayDate);
                    baseTitle += ` - ${dayStr}`;
                }

                return baseTitle;
            })(),
            top: 0
        },
        tooltip: {
            trigger: 'axis',
            formatter: function (params) {
                const ts = params[0].value[0];
                let output = `${formatTime(ts)}<br>`;
                for (const p of params) {
                    output += `${p.marker} ${p.seriesName}: ${p.value[1]} °C<br>`;
                }
                return output;
            }
        },
        legend: {
            data: series.map(s => s.name),
            top: 40,
            selectedMode: series.length <= 1 ? false : true
        },
        grid: {
            top: 200,
            left: 100,
            right: 100,
            bottom: 100
        },
        xAxis: {
            type: 'time',
            name: 'Time',
            axisLabel: {
                rotate: 45,
                formatter: function (value) {
                    return formatTime(value);
                }
            }
        },
        yAxis: {
            type: 'value',
            name: 'Temperature (°C)'
        },
        series: series
    };

    // Add markLine for day breaks if we have any
    if (markLines.length > 0) {
        option.series.push({
            name: 'Day Breaks',
            type: 'line',
            showSymbol: false,
            showLine: false,
            data: [],
            markLine: {
                symbol: 'none',
                data: markLines,
                lineStyle: {
                    type: 'dotted',
                    color: '#bbb',
                    width: 1
                },
                label: { show: false }
            }
        });
    }

    chart.setOption(option, true);
}

// ==========================
// Render the Air Quality chart
// ==========================
function updateAQChart() {
    if (!aqChart) return;

    // Convert seconds->ms for ECharts time axis
    const toMs = arr => (arr || []).map(([ts, v]) => [ts * 1000, v]);

    const series = [
        { name: 'PM2.5', data: toMs(aqRaw.pm25), unit: 'µg/m³', yAxisIndex: 0 },
        { name: 'PM10',  data: toMs(aqRaw.pm10), unit: 'µg/m³', yAxisIndex: 1 },
        { name: 'O₃',    data: toMs(aqRaw.o3),   unit: 'ppb',   yAxisIndex: 2 },
        { name: 'NO₂',   data: toMs(aqRaw.no2),  unit: 'ppb',   yAxisIndex: 3 },
        { name: 'CO',    data: toMs(aqRaw.co),   unit: 'ppm',   yAxisIndex: 4 },
        { name: 'AQI',   data: toMs(aqRaw.aqi),  unit: '',      yAxisIndex: 5 },
    ].map(s => ({
        name: s.name,
        type: 'line',
        showSymbol: false,
        encode: { x: 0, y: 1 },
        yAxisIndex: s.yAxisIndex,
        data: s.data
    }));

    const yAxes = [
        { type: 'value', name: 'PM2.5 (µg/m³)', axisLabel: { formatter: v => `${v}` } },
        { type: 'value', name: 'PM10 (µg/m³)',  axisLabel: { formatter: v => `${v}` }, gridIndex: 0, position: 'right' },
        { type: 'value', name: 'O₃ (ppb)',      axisLabel: { formatter: v => `${v}` }, gridIndex: 0, position: 'left'  },
        { type: 'value', name: 'NO₂ (ppb)',     axisLabel: { formatter: v => `${v}` }, gridIndex: 0, position: 'right' },
        { type: 'value', name: 'CO (ppm)',      axisLabel: { formatter: v => `${v}` }, gridIndex: 0, position: 'left'  },
        { type: 'value', name: 'AQI',           axisLabel: { formatter: v => `${v}` }, gridIndex: 0, position: 'right' }
    ];

    // Make alternate axes not draw overlapping grid lines
    yAxes.forEach((ax, i) => {
        ax.splitLine = { show: i === 0 }; // keep one set
    });

    const option = {
        title: { text: 'Air Quality (multi-axis)', top: 0 },
        tooltip: {
            trigger: 'axis',
            formatter: params => {
                if (!params || !params.length) return '';
                const ts = params[0].value[0];
                const d = new Date(ts);
                const time = new Intl.DateTimeFormat(undefined, {
                    weekday: 'short', month: 'short', day: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                }).format(d);
                return params.reduce((out, p) => {
                    return out + `${p.marker} ${p.seriesName}: ${p.value[1]}${unitFor(p.seriesName)}<br>`;
                }, `${time}<br>`);
            }
        },
        legend: { top: 40 },
        grid:   { top: 120, left: 80, right: 80, bottom: 80 },
        xAxis:  { type: 'time', axisLabel: { rotate: 45 } },
        yAxis:  yAxes,
        series: series,
        axisPointer: { // helps link with temp chart
            link: [{ xAxisIndex: 'all' }],
            snap: true
        }
    };

    aqChart.setOption(option, true);

    // Keep charts linked (crosshair/zoom)
    try { echarts.connect([chart, aqChart]); } catch(_) {}
}

// Load all available devices for the dropdown
function loadAllDevices() {
    fetch('/api/v1/status')
        .then(response => response.json())
        .then(data => {
            allDevices = data.devices || [];
            updateDeviceDropdown();
        })
        .catch(error => {
            console.error('Error loading devices:', error);
        });
}

// Update the device dropdown with available devices
function updateDeviceDropdown() {
    const select = document.getElementById('addDeviceSelect');
    if (!select) return;

    // Clear existing options except the first one
    select.innerHTML = '<option value="">Select a device...</option>';

    // Get currently displayed device IDs
    const currentIds = currentDeviceIds || [];

    // Filter out devices that are already displayed
    const availableDevices = allDevices.filter(device => !currentIds.includes(device.device_id));

    // Sort by device name
    availableDevices.sort((a, b) => a.device_name.localeCompare(b.device_name));

    // Add options for available devices
    availableDevices.forEach(device => {
        const option = document.createElement('option');
        option.value = device.device_id;
        option.textContent = `${device.device_name} (${device.device_id})`;
        select.appendChild(option);
    });
}

// Add a device to the current chart
function addDeviceToChart(deviceId) {
    // Initialize currentDeviceIds if it's null
    if (!currentDeviceIds) {
        currentDeviceIds = [];
    }
    // Add the device if it's not already included
    if (!currentDeviceIds.includes(deviceId)) {
        currentDeviceIds.push(deviceId);
        // Reload data with the new device
        loadData(currentDeviceIds, currentStart, currentEnd);
        // Update the dropdown to reflect the change
        updateDeviceDropdown();
    }
}


// ----------------------------------
// Reuse the same date range for both
// ----------------------------------
function setPickersFromRange() {
    if (currentStart && currentEnd) {
        const sd = new Date(currentStart * 1000);
        const ed = new Date(currentEnd   * 1000);
        const pad = n => String(n).padStart(2, '0');
        const toISODate = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
        document.getElementById('startDate').value = toISODate(sd);
        document.getElementById('endDate').value   = toISODate(ed);
    }
}

function pickersToRangeAndReload() {
    const sd = document.getElementById('startDate').value; // yyyy-mm-dd
    const ed = document.getElementById('endDate').value;

    if (sd) {
        const s = new Date(sd + 'T00:00:00');
        currentStart = Math.floor(s.getTime() / 1000);
    }
    if (ed) {
        const e = new Date(ed + 'T23:59:59');
        currentEnd = Math.floor(e.getTime() / 1000);
    }

    // Reload both charts’ data with the shared range
    Promise.all([
        loadData(currentDeviceIds, currentStart, currentEnd),
        loadAirQuality(currentDeviceIds, currentStart, currentEnd)
    ]).then(() => {
        // When both updated, keep crosshair synced
        try { echarts.connect([chart, aqChart]); } catch(_) {}
    });
}

// Set up event listeners
function setupEventListeners() {
    // Device dropdown handler
    document.getElementById('addDeviceSelect').addEventListener('change', function() {
        const selectedDeviceId = parseInt(this.value);
        if (selectedDeviceId) {
            addDeviceToChart(selectedDeviceId);
            this.value = ''; // Reset selection
        }
    });

    // Temporal button handlers
    document.getElementById('dayBtn').addEventListener('click', () => {
        const now = Math.floor(Date.now() / 1000);
        const dayAgo = now - 24 * 60 * 60;
        currentStart = dayAgo;
        currentEnd = now;
        setPickersFromRange();
        loadData(currentDeviceIds, currentStart, currentEnd);
    });

    document.getElementById('weekBtn').addEventListener('click', () => {
        const now = Math.floor(Date.now() / 1000);
        const weekAgo = now - 7 * 24 * 60 * 60;
        currentStart = weekAgo;
        currentEnd = now;
        setPickersFromRange();
        loadData(currentDeviceIds, currentStart, currentEnd);
    });

    document.getElementById('monthBtn').addEventListener('click', () => {
        const now = Math.floor(Date.now() / 1000);
        const monthAgo = now - 30 * 24 * 60 * 60;
        currentStart = monthAgo;
        currentEnd = now;
        setPickersFromRange();
        loadData(currentDeviceIds, currentStart, currentEnd);
    });

    // Date pickers
    document.getElementById('startDate').addEventListener('change', pickersToRangeAndReload);
    document.getElementById('endDate').addEventListener('change', pickersToRangeAndReload);

    /****************************************************************
     *** CSV Export
     ****************************************************************/
    // CSV Export start
    document.getElementById('downloadCsv').addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('#checkboxes input[type=checkbox]');
        const visibleSeries = [];

        if (currentDeviceIds) {
            visibleSeries.push(...rawData);
        } else {
            checkboxes.forEach((cb, i) => {
                if (cb.checked) {
                    visibleSeries.push(rawData[i]);
                }
            });
        }

        if (visibleSeries.length === 0) {
            alert('No data to export');
            return;
        }

        // Create CSV content
        let csvContent = 'data:text/csv;charset=utf-8,';
        csvContent += 'Time,' + visibleSeries.map(s => s.name).join(',') + '\n';

        // Get all unique timestamps
        const allTimestamps = new Set();
        visibleSeries.forEach(series => {
            series.data.forEach(([ts]) => allTimestamps.add(ts));
        });

        const sortedTimestamps = Array.from(allTimestamps).sort((a, b) => a - b);

        // Create rows
        sortedTimestamps.forEach(ts => {
            const row = [formatTime(ts * 1000)];
            visibleSeries.forEach(series => {
                const dataPoint = series.data.find(([t]) => t === ts);
                row.push(dataPoint ? dataPoint[1] : '');
            });
            csvContent += row.join(',') + '\n';
        });

        // Download the file
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement('a');
        link.setAttribute('href', encodedUri);
        link.setAttribute('download', 'temperature_data.csv');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    });

    /****************************************************************
     *** END OF CSV EXPORT
     ****************************************************************/
}

// ===============================
// Default: last 7 days on load
// ===============================
// After your initial loadData() call completes, also load AQ, then fill pickers:
document.addEventListener('DOMContentLoaded', function() {
    // If you want default to last 7 days immediately:
    const now = Math.floor(Date.now() / 1000);
    currentStart = now - 7 * 24 * 60 * 60;
    currentEnd   = now;

    Promise.all([
        loadData(currentDeviceIds, currentStart, currentEnd),
        loadAirQuality(currentDeviceIds, currentStart, currentEnd)
    ]).then(() => {
        setPickersFromRange();
        try { echarts.connect([chart, aqChart]); } catch(_) {}
    });
});
