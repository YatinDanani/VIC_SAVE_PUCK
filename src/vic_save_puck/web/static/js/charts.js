/* Chart.js: Forecast vs Actual bar chart + Cumulative Drift line */

const Charts = {
    forecastChart: null,
    driftChart: null,
    annotations: [],

    init() {
        Chart.defaults.color = '#71717a';
        Chart.defaults.borderColor = '#2a2d3a';
        Chart.defaults.font.family = "'SF Mono', 'Cascadia Code', monospace";
        Chart.defaults.font.size = 11;

        this._initForecastChart();
        this._initDriftChart();
    },

    _initForecastChart() {
        const ctx = document.getElementById('forecast-chart').getContext('2d');
        this.forecastChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Forecast',
                        data: [],
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        borderWidth: 1,
                        borderRadius: 3,
                    },
                    {
                        label: 'Actual',
                        data: [],
                        backgroundColor: 'rgba(249, 115, 22, 0.7)',
                        borderColor: 'rgba(249, 115, 22, 1)',
                        borderWidth: 1,
                        borderRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { boxWidth: 12, padding: 16 },
                    },
                    tooltip: {
                        callbacks: {
                            afterBody: (items) => {
                                if (items.length >= 2) {
                                    const fc = items[0].raw;
                                    const act = items[1].raw;
                                    if (fc > 0) {
                                        const drift = ((act - fc) / fc * 100).toFixed(1);
                                        return `Drift: ${drift > 0 ? '+' : ''}${drift}%`;
                                    }
                                }
                                return '';
                            }
                        }
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { maxRotation: 0 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(42, 45, 58, 0.5)' },
                    },
                },
            },
        });
    },

    _initDriftChart() {
        const ctx = document.getElementById('drift-chart').getContext('2d');
        this.driftChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Cumulative Drift',
                        data: [],
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                        pointBackgroundColor: '#f97316',
                    },
                    {
                        label: '+15% (Green)',
                        data: [],
                        borderColor: 'rgba(34, 197, 94, 0.3)',
                        borderWidth: 1,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false,
                    },
                    {
                        label: '-15% (Green)',
                        data: [],
                        borderColor: 'rgba(34, 197, 94, 0.3)',
                        borderWidth: 1,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false,
                    },
                    {
                        label: '+30% (Yellow)',
                        data: [],
                        borderColor: 'rgba(234, 179, 8, 0.3)',
                        borderWidth: 1,
                        borderDash: [2, 2],
                        pointRadius: 0,
                        fill: false,
                    },
                    {
                        label: '-30% (Yellow)',
                        data: [],
                        borderColor: 'rgba(234, 179, 8, 0.3)',
                        borderWidth: 1,
                        borderDash: [2, 2],
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => {
                                if (item.datasetIndex === 0) {
                                    return `Drift: ${(item.raw * 100).toFixed(1)}%`;
                                }
                                return null;
                            }
                        }
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { maxRotation: 0 },
                    },
                    y: {
                        grid: { color: 'rgba(42, 45, 58, 0.5)' },
                        ticks: {
                            callback: (val) => `${(val * 100).toFixed(0)}%`,
                        },
                    },
                },
            },
        });
    },

    reset(forecastSummary) {
        this.forecastChart.data.labels = [];
        this.forecastChart.data.datasets[0].data = [];
        this.forecastChart.data.datasets[1].data = [];
        this.forecastChart.update('none');

        this.driftChart.data.labels = [];
        for (let ds of this.driftChart.data.datasets) ds.data = [];
        this.driftChart.update('none');

        this.annotations = [];
    },

    addWindow(data) {
        const label = `T${data.time_window >= 0 ? '+' : ''}${data.time_window}`;

        // Bar chart
        this.forecastChart.data.labels.push(label);
        this.forecastChart.data.datasets[0].data.push(data.forecast_qty);
        this.forecastChart.data.datasets[1].data.push(data.actual_qty);
        this.forecastChart.update('none');

        // Drift chart
        this.driftChart.data.labels.push(label);
        this.driftChart.data.datasets[0].data.push(data.cumulative_drift);
        this.driftChart.data.datasets[1].data.push(0.15);
        this.driftChart.data.datasets[2].data.push(-0.15);
        this.driftChart.data.datasets[3].data.push(0.30);
        this.driftChart.data.datasets[4].data.push(-0.30);
        this.driftChart.update('none');
    },

    addAnnotation(timeWindow, type) {
        this.annotations.push({ timeWindow, type });
        // Visual feedback: add a colored point to the drift chart at this window
        const labels = this.driftChart.data.labels;
        const label = `T${timeWindow >= 0 ? '+' : ''}${timeWindow}`;
        const idx = labels.indexOf(label);
        if (idx >= 0) {
            // Flash the bar chart bar
            const barColors = [...this.forecastChart.data.datasets[1].backgroundColor];
            if (typeof barColors === 'string') return;
        }
    },
};
