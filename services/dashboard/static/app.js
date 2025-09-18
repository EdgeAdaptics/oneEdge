const metricsTableBody = document.querySelector('#metrics-table tbody');
const metricSelect = document.querySelector('#metric-select');
const machineSelect = document.querySelector('#machine-select');
const alertsList = document.querySelector('#alerts-list');
let chart;
let metricsIndex = {};

async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleString();
}

function renderMetrics(rows) {
    metricsTableBody.innerHTML = '';
    metricsIndex = {};
    const machines = new Set();
    const metrics = new Set();

    rows.forEach((row) => {
        const tr = document.createElement('tr');
        const machine = row.topic.split('/').pop();
        tr.innerHTML = `
            <td>${machine}</td>
            <td>${row.metric}</td>
            <td>${row.value?.toFixed(2) ?? '-'}</td>
            <td>${formatTimestamp(row.timestamp)}</td>
        `;
        metricsTableBody.appendChild(tr);
        machines.add(machine);
        metrics.add(row.metric);
        const key = `${machine}:${row.metric}`;
        metricsIndex[key] = row.topic;
    });

    metricSelect.innerHTML = Array.from(metrics)
        .sort()
        .map((metric) => `<option value="${metric}">${metric}</option>`) // Keep as string
        .join('');

    machineSelect.innerHTML = Array.from(machines)
        .sort()
        .map((machine) => `<option value="${machine}">${machine}</option>`)
        .join('');

    if (metrics.size && machines.size) {
        updateChart();
    }
}

async function updateChart() {
    if (!metricSelect.value || !machineSelect.value) {
        return;
    }
    const key = `${machineSelect.value}:${metricSelect.value}`;
    const topic = metricsIndex[key];
    if (!topic) return;
    const data = await fetchJSON(`/api/metrics/history?metric=${encodeURIComponent(metricSelect.value)}&topic=${encodeURIComponent(topic)}`);
    const labels = data.map((row) => new Date(row.timestamp).toLocaleTimeString());
    const values = data.map((row) => row.value);

    if (!chart) {
        const ctx = document.querySelector('#metric-chart').getContext('2d');
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: `${metricSelect.value} (${machineSelect.value})`,
                        data: values,
                        borderColor: '#22d3ee',
                        tension: 0.3,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        ticks: { color: '#94a3b8' },
                    },
                    y: {
                        ticks: { color: '#94a3b8' },
                    },
                },
            },
        });
    } else {
        chart.data.labels = labels;
        chart.data.datasets[0].label = `${metricSelect.value} (${machineSelect.value})`;
        chart.data.datasets[0].data = values;
        chart.update();
    }
}

function renderAlerts(alerts) {
    alertsList.innerHTML = '';
    alerts.forEach(addAlertToList);
}

function addAlertToList(alert) {
    const li = document.createElement('li');
    li.classList.add('alert-item', alert.severity ?? 'warning');
    li.innerHTML = `
        <div>
            <strong>${alert.message}</strong>
            <div class="meta">${alert.rule} · ${alert.topic} · ${formatTimestamp(alert.timestamp)}</div>
        </div>
        <div>
            ${alert.acknowledged ? '<span class="meta">Acknowledged</span>' : '<button data-id="' + alert.id + '">Acknowledge</button>'}
        </div>
    `;
    const button = li.querySelector('button');
    if (button) {
        button.addEventListener('click', () => ackAlert(button.dataset.id));
    }
    alertsList.prepend(li);
}

async function ackAlert(alertId) {
    await fetch(`/api/alerts/${alertId}/ack`, { method: 'POST' });
    initialiseAlerts();
}

async function initialiseAlerts() {
    const alerts = await fetchJSON('/api/alerts');
    renderAlerts(alerts);
}

function subscribeToAlerts() {
    const source = new EventSource('/api/alerts/stream');
    source.onmessage = (event) => {
        try {
            const alert = JSON.parse(event.data);
            addAlertToList(alert);
        } catch (err) {
            console.error('Failed to parse alert', err);
        }
    };
}

async function init() {
    try {
        const metrics = await fetchJSON('/api/metrics/latest?limit=50');
        renderMetrics(metrics);
        await initialiseAlerts();
        subscribeToAlerts();
    } catch (err) {
        console.error('Failed to initialise dashboard', err);
    }
}

metricSelect.addEventListener('change', updateChart);
machineSelect.addEventListener('change', updateChart);

document.addEventListener('DOMContentLoaded', init);
