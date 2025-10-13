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

// Air Quality Display and Units
AQI_UNITS =
    {'PM2.5':'PM2.5 µg/m³',
     'PM10': 'PM10 µg/m³',
     'O3': 'O₃ ppb',
     'NO2': 'NO₂ ppb',
     'CO':  'CO ppm'};


function loadAirQuality() {
    let url = AIQ_ENDPOINT;
    const params = new URLSearchParams();
    params.append('start', currentStart);
    params.append('end', currentEnd);
    url += '?' + params.toString();

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
    try { echarts.connect([tempChart, aqChart]); } catch(_) {}
}
