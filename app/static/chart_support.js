// chart.js - Temperature chart functionality

let chart;
let rawData = []; // original data from API
let currentStart = null;
let currentEnd = null;
let currentDeviceIds = null; // for device support (single or multiple)
let allDevices = []; // all available devices for dropdown

// Initialize chart when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    chart = echarts.init(document.getElementById('main'));

    // Get device_ids from template variable (will be set by chart.html)
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

// Load data from API with optional parameters
function loadData(deviceIds = null, start = null, end = null) {
    let url = '/api/v1/temperature';
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
        recordCountElement.style.cssText = 'margin: 10px 0; padding: 5px; background: #f0f0f0; border-radius: 3px; font-family: monospace;';

        // Find the controls element
        const controlsElement = document.getElementById('controls');
        if (controlsElement) {
            // Insert at the beginning of controls, before the flex container
            controlsElement.insertBefore(recordCountElement, controlsElement.firstChild);
        }
    }
    recordCountElement.textContent = `Records loaded: ${totalRecords}`;
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
        loadData(currentDeviceIds, currentStart, currentEnd);
    });

    document.getElementById('weekBtn').addEventListener('click', () => {
        const now = Math.floor(Date.now() / 1000);
        const weekAgo = now - 7 * 24 * 60 * 60;
        currentStart = weekAgo;
        currentEnd = now;
        loadData(currentDeviceIds, currentStart, currentEnd);
    });

    document.getElementById('monthBtn').addEventListener('click', () => {
        const now = Math.floor(Date.now() / 1000);
        const monthAgo = now - 30 * 24 * 60 * 60;
        currentStart = monthAgo;
        currentEnd = now;
        loadData(currentDeviceIds, currentStart, currentEnd);
    });

    // CSV Export
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
}