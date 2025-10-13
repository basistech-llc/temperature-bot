// chart_support.js - AQI and Temperature chart functionality

let tempChart = null;               // temperature chart
let tempData = [];            // original data from API
let aqiChart = null;
let aqiData = [];
let currentStart = null;        // time_t
let currentEnd = null;          // time_t
let currentDeviceIds = []; // current devices to load. [] means load them all
let allDevices = []; // all available devices for dropdown
const TEMP_ENDPOINT = '/api/v1/temperature';
const AIQ_ENDPOINT = '/api/v1/air_quality';

/****************************************************************
 *** Date selection
 ****************************************************************/
function setPickersFromRange() {
    if (currentStart && currentEnd) {
        const sd = new Date(currentStart * 1000);
        const ed = new Date(currentEnd   * 1000);
        const pad = n => String(n).padStart(2, '0');
        const toISODate = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
        document.getElementById('startDate').value = toISODate(sd);
        document.getElementById('endDate').value   = toISODate(ed);
    }
    reloadData();
}

function pickersChanged() {
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
    reloadData();
}

function setTimePrevDays(days) {
    currentEnd = Math.floor(Date.now() / 1000);
    currentStart = currentEnd - days * 24 * 60 * 60;
    setPickersFromRange();
}

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
function updateTempRecordCount() {
    let totalRecords = 0;
    tempData.forEach(series => { totalRecords += series.data.length; }); // count records in each series
    let recordCountElement = document.getElementById('record-count');
    if (recordCountElement) {
        recordCountElement.textContent = `Total temperature datapoints: ${totalRecords}`;
    } else {
        console.error("no element record-count");
    }
}


/****************************************************************/

// Load data from API with optional parameters
function loadTempData() {
    let url = TEMP_ENDPOINT;
    const params = new URLSearchParams();

    // Support single device or multiple devices
    if (currentDeviceIds.length > 0) {
        params.append('device_ids', currentDeviceIds.join(','));
    }
    params.append('start', currentStart);
    params.append('end', currentEnd);
    url += '?' + params.toString();

    console.log("Fetch ",url);
    fetch(url)
        .then(response => response.json())
        .then(json => {
            tempData = json.series;
            console.log("tempData=",tempData);

            // Expected shape (example):
            // [{name: "Sensor 1", data:[[ts,val],[ts2,val2],[ts3,val3]...]},
            // {name: "Sensor 2", data:[[ts,val],[ts2,val2],[ts3,val3]...]},... ]

            // Draw checkboxes if not filtering by device.
            // This causes all devices to be shown
            if (currentDeviceIds.length==0) {
                const checkboxContainer = document.getElementById('checkboxes');
                checkboxContainer.innerHTML = '';
                tempData.forEach((series, index) => {
                    const id = `checkbox-${index}`;
                    const wrapper = document.createElement('span');
                    wrapper.style.whiteSpace = 'nowrap';   // keep label on one line with its checkbox
                    wrapper.style.marginRight = '1em';     // small gap before next checkbox group

                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.id = id;
                    checkbox.checked = true;

                    const label = document.createElement('label');
                    label.htmlFor = id;
                    label.innerText = series.name;

                    console.log("creating checkbox for series ",series.name);

                    checkbox.addEventListener('change', updateTempChart);
                    wrapper.appendChild(checkbox);
                    wrapper.appendChild(label);
                    checkboxContainer.appendChild(wrapper);
                });
            }
            // Update record count display
            updateTempRecordCount();
            updateTempChart();
        });
}

function updateTempChart() {
    // Called when a checkbox changes or data changes
    console.log("updateTempChart");
    const checkboxes = document.querySelectorAll('#checkboxes input[type=checkbox]');
    const series = [];

    // Show only checked series
    checkboxes.forEach((cb, i) => {
        if (cb.checked) {
            series.push({
                name: tempData[i].name,
                type: 'line',
                showSymbol: false,
                data: tempData[i].data.map(([ts, val]) => [ts * 1000, val]) // convert to ms
            });
        }
    });

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

    console.log("minTs=",minTs,"maxTs=",maxTs);

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
        grid: { top: 200, left: 100, right: 100, bottom: 100 },
        xAxis: { type: 'time', name: 'Time',
                 axisLabel: {
                     rotate: 45,
                     formatter: function (value) { return formatTime(value); } }
               },
        yAxis: { type: 'value', name: 'Temperature (°C)' },
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
    tempChart.setOption(option, { notMerge: true});
}


/****************************************************************/

// Set up event listeners
function setupEventListeners() {
    // Temporal button handlers
    document.getElementById('dayBtn').addEventListener('click', () => {
        setTimePrevDays(1);
    });

    document.getElementById('weekBtn').addEventListener('click', () => {
        setTimePrevDays(7);
    });

    document.getElementById('monthBtn').addEventListener('click', () => {
        setTimePrevDays(31);
    });

    // Date pickers
    document.getElementById('startDate').addEventListener('change', pickersChanged);
    document.getElementById('endDate').addEventListener('change', pickersChanged);

    /****************************************************************
     *** CSV Export
     ****************************************************************/
    // CSV Export start
    document.getElementById('downloadCsv').addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('#checkboxes input[type=checkbox]');
        const visibleSeries = [];

        if (currentDeviceIds) {
            visibleSeries.push(...tempData);
        } else {
            checkboxes.forEach((cb, i) => {
                if (cb.checked) {
                    visibleSeries.push(tempData[i]);
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

function reloadData() {
    // Reload both charts’ data with the shared range
    console.log("reloadData");
    Promise.all([
        loadTempData(),
        // loadAirQualityData()
    ]).then(() => {
        // When both updated, keep crosshair synced
        // try { echarts.connect([tempChart  aqChart ]); } catch(_) {}
    });
}



// ===============================
// Default: last 7 days on load
// ===============================
// After your initial loadData() call completes, also load AQ, then fill pickers:
document.addEventListener('DOMContentLoaded', function() {
    setTimePrevDays(7);// Initialize to 1 week of date
    console.log("calling echarts.init");
    tempChart = echarts.init(document.getElementById('temp-chart')); // // Temperature chart
    console.log("back. tempChart=",tempChart);
    //aqChart   = echarts.init(document.getElementById('airquality'));

    reloadData();
    // Load both charts then set
    loadTempData();

    // Set up event listeners
    setupEventListeners();
});
