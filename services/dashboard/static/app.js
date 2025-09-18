const metricsTableBody = document.querySelector('#metrics-table tbody');
const metricSelect = document.querySelector('#metric-select');
const machineSelect = document.querySelector('#machine-select');
const alertsList = document.querySelector('#alerts-list');
const devicesTableBody = document.querySelector('#devices-table tbody');
const attentionTableBody = document.querySelector('#attention-table tbody');
const deviceForm = document.querySelector('#device-form');
const deviceFeedback = document.querySelector('#device-feedback');
const authMethodSelect = document.querySelector('#device-auth-method');
const authIdInput = document.querySelector('#device-auth-id');
const allowedEndpointsInput = document.querySelector('#device-allowed-endpoints');
const rotationInput = document.querySelector('#device-rotation');
const initialSecretInput = document.querySelector('#device-initial-secret');
const staticKeyInput = document.querySelector('#device-static-key');
const hardwareInput = document.querySelector('#device-hardware');
const publicKeyInput = document.querySelector('#device-public-key');
const policyTemplateInput = document.querySelector('#device-policy');
const metadataInput = document.querySelector('#device-metadata');
const navButtons = document.querySelectorAll('[data-nav]');
const dropdown = document.querySelector('.nav-dropdown');
const viewContainers = document.querySelectorAll('.view');

let chart;
let metricsIndex = {};
let metricsPollHandle;
let devicesPollHandle;
let devicesState = [];

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        let message = `Request failed: ${response.status}`;
        try {
            message = (await response.text()) || message;
        } catch (err) {
            /* ignore */
        }
        throw new Error(message);
    }
    if (response.status === 204) {
        return null;
    }
    return response.json();
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleString();
}

function showFeedback(message, tone = 'info') {
    if (!deviceFeedback) return;
    deviceFeedback.textContent = message;
    if (tone === 'error') {
        deviceFeedback.style.color = '#f87171';
    } else if (tone === 'success') {
        deviceFeedback.style.color = '#22d3ee';
    } else {
        deviceFeedback.style.color = '#94a3b8';
    }
}

function setActiveView(view) {
    viewContainers.forEach((container) => {
        if (container.dataset.view === view) {
            container.classList.remove('hidden');
            container.classList.add('active');
        } else {
            container.classList.remove('active');
            container.classList.add('hidden');
        }
    });
    navButtons.forEach((button) => {
        button.classList.toggle('active', button.dataset.nav === view);
    });
}

navButtons.forEach((button) => {
    button.addEventListener('click', () => {
        const view = button.dataset.nav;
        if (!view) return;
        setActiveView(view);
        if (dropdown) dropdown.classList.remove('open');
    });
});

const dropdownToggle = dropdown?.querySelector('.nav-link');
dropdownToggle?.addEventListener('click', () => {
    dropdown.classList.toggle('open');
});

document.addEventListener('click', (event) => {
    if (!dropdown) return;
    if (dropdown.contains(event.target)) return;
    dropdown.classList.remove('open');
});

setActiveView('overview');

function renderMetrics(rows) {
    const previousMetric = metricSelect.value;
    const previousMachine = machineSelect.value;

    metricsTableBody.innerHTML = '';
    metricsIndex = {};
    const machines = new Set();
    const metrics = new Set();

    rows.forEach((row) => {
        const tr = document.createElement('tr');
        const topicParts = row.topic.split('/');
        const machine = topicParts[topicParts.length - 1];
        tr.innerHTML = `
            <td>${machine}</td>
            <td>${row.metric}</td>
            <td>${row.value?.toFixed?.(2) ?? '-'}</td>
            <td>${formatTimestamp(row.timestamp)}</td>
        `;
        metricsTableBody.appendChild(tr);
        machines.add(machine);
        metrics.add(row.metric);
        const key = `${machine}:${row.metric}`;
        metricsIndex[key] = row.topic;
    });

    const metricOptions = Array.from(metrics).sort();
    const machineOptions = Array.from(machines).sort();

    metricSelect.innerHTML = metricOptions
        .map((metric) => `<option value="${metric}">${metric}</option>`)
        .join('');
    machineSelect.innerHTML = machineOptions
        .map((machine) => `<option value="${machine}">${machine}</option>`)
        .join('');

    if (previousMetric && metricOptions.includes(previousMetric)) {
        metricSelect.value = previousMetric;
    }
    if (previousMachine && machineOptions.includes(previousMachine)) {
        machineSelect.value = previousMachine;
    }

    if (metricSelect.value && machineSelect.value) {
        updateChart().catch((err) => console.error('Failed to refresh chart', err));
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

function renderAlerts(alerts) {
    alertsList.innerHTML = '';
    alerts.forEach(addAlertToList);
}

async function ackAlert(alertId) {
    try {
        await fetchJSON('/api/alerts/' + alertId + '/ack', { method: 'POST' });
        initialiseAlerts();
    } catch (err) {
        console.error('Failed to acknowledge alert', err);
    }
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

function renderDevices(devices) {
    devicesTableBody.innerHTML = '';
    devicesState = devices;
    devices.forEach((device) => {
        const tr = document.createElement('tr');
        tr.dataset.deviceId = device.device_id;
        tr.classList.add('device-row');
        if (device.quarantined) tr.classList.add('device-quarantined');
        if (device.needs_rotation) tr.classList.add('device-needs-rotation');
        if (device.stale) tr.classList.add('device-stale');
        if (device.attention_required) tr.classList.add('device-attention');

        const flags = [];
        if (device.quarantined) flags.push('Quarantined');
        if (device.needs_rotation) flags.push('Rotate Keys');
        if (device.stale) flags.push('Stale');
        if (device.challenge_pending) flags.push('Challenge Pending');

        tr.innerHTML = `
            <td>${device.device_id}</td>
            <td>${device.name}</td>
            <td>${device.auth_method ?? '-'}</td>
            <td>${device.status ?? '-'}</td>
            <td>${formatTimestamp(device.last_seen_at)}</td>
            <td>${formatTimestamp(device.last_rotated_at)}</td>
            <td>${flags.join(', ') || 'Healthy'}</td>
            <td class="device-actions">
                <button class="device-action" data-action="challenge">Challenge</button>
                <button class="device-action" data-action="rotate">Rotate</button>
                <button class="device-action" data-action="${device.quarantined ? 'authorize' : 'quarantine'}">${device.quarantined ? 'Authorize' : 'Quarantine'}</button>
                <button class="device-action" data-action="delete">Delete</button>
            </td>
        `;
        devicesTableBody.appendChild(tr);
    });
    renderAttentionTable();
}

function renderAttentionTable() {
    if (!attentionTableBody) return;
    attentionTableBody.innerHTML = '';
    const attentionDevices = devicesState.filter((device) => device.attention_required);
    if (!attentionDevices.length) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="5">All devices healthy</td>';
        attentionTableBody.appendChild(tr);
        return;
    }
    attentionDevices.forEach((device) => {
        const flags = [];
        if (device.quarantined) flags.push('Quarantined');
        if (device.needs_rotation) flags.push('Rotation overdue');
        if (device.stale) flags.push('Stale');
        if (device.challenge_pending) flags.push('Challenge pending');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${device.device_id}</td>
            <td>${device.status ?? '-'}</td>
            <td>${flags.join(', ')}</td>
            <td>${formatTimestamp(device.last_seen_at)}</td>
            <td>${formatTimestamp(device.challenge_expires_at)}</td>
        `;
        attentionTableBody.appendChild(tr);
    });
}

async function refreshDevices() {
    try {
        const devices = await fetchJSON('/api/devices');
        renderDevices(devices);
    } catch (err) {
        console.error('Device refresh failed', err);
    }
}

async function refreshMetrics() {
    try {
        const metrics = await fetchJSON('/api/metrics/latest?limit=50');
        renderMetrics(metrics);
    } catch (err) {
        console.error('Metric refresh failed', err);
    }
}

function startAutoRefresh() {
    metricsPollHandle = setInterval(refreshMetrics, 5000);
    devicesPollHandle = setInterval(refreshDevices, 15000);
}

function stopAutoRefresh() {
    clearInterval(metricsPollHandle);
    clearInterval(devicesPollHandle);
}

deviceForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(deviceForm);

    const payload = {
        device_id: formData.get('device_id')?.toString().trim(),
        name: formData.get('name')?.toString().trim(),
        device_type: formData.get('device_type')?.toString().trim() || null,
        location: formData.get('location')?.toString().trim() || null,
        status: formData.get('status')?.toString().trim() || 'inactive',
        auth_method: authMethodSelect?.value || 'pre_shared_key',
        auth_id: authIdInput?.value.trim() || null,
        rotation_interval_hours: rotationInput?.value ? Number.parseInt(rotationInput.value, 10) : null,
        quarantined: false,
    };

    const allowedEndpointsValue = allowedEndpointsInput?.value.trim();
    payload.allowed_endpoints = allowedEndpointsValue
        ? allowedEndpointsValue.split(',').map((item) => item.trim()).filter(Boolean)
        : [];

    if (staticKeyInput?.value.trim()) {
        payload.device_static_key = staticKeyInput.value.trim();
    }
    if (hardwareInput?.value.trim()) {
        payload.hardware_fingerprint = hardwareInput.value.trim();
    }
    if (publicKeyInput?.value.trim()) {
        payload.device_public_key = publicKeyInput.value.trim();
    }

    if (initialSecretInput?.value.trim()) {
        payload.initial_secret = initialSecretInput.value.trim();
    }

    const metadataText = metadataInput?.value.trim();
    if (metadataText) {
        try {
            payload.metadata = JSON.parse(metadataText);
        } catch (err) {
            showFeedback('Metadata must be valid JSON.', 'error');
            return;
        }
    } else {
        payload.metadata = null;
    }

    const policyText = policyTemplateInput?.value.trim();
    if (policyText) {
        try {
            payload.policy_template = JSON.parse(policyText);
        } catch (err) {
            showFeedback('Policy template must be valid JSON.', 'error');
            return;
        }
    } else {
        payload.policy_template = null;
    }

    try {
        const response = await fetchJSON('/api/devices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        let feedback = 'Device saved successfully';
        if (response.bootstrap_secret) {
            feedback += ` | Bootstrap secret: ${response.bootstrap_secret}`;
        }
        showFeedback(feedback, 'success');
        deviceForm.reset();
        refreshDevices();
    } catch (err) {
        console.error('Device provisioning failed', err);
        showFeedback(err.message, 'error');
    }
});

devicesTableBody?.addEventListener('click', async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.classList.contains('device-action')) return;
    const action = target.dataset.action;
    const row = target.closest('tr');
    if (!row) return;
    const deviceId = row.dataset.deviceId;
    if (!deviceId) return;

    try {
        if (action === 'challenge') {
            const result = await fetchJSON('/api/devices/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: deviceId, request_challenge: true }),
            });
            if (result.challenge) {
                const expires = result.expires_at ? ` (expires ${formatTimestamp(result.expires_at)})` : '';
                showFeedback(`Challenge for ${deviceId}: ${result.challenge}${expires}`, 'info');
            } else {
                showFeedback(`Challenge issued for ${deviceId}`, 'info');
            }
        } else if (action === 'rotate') {
            const response = await fetchJSON(`/api/devices/${encodeURIComponent(deviceId)}/rotate`, { method: 'POST' });
            if (response.session_secret) {
                showFeedback(`New session secret for ${deviceId}: ${response.session_secret}`, 'success');
            } else {
                showFeedback(`Rotation request accepted for ${deviceId}`, 'success');
            }
        } else if (action === 'quarantine') {
            await fetchJSON(`/api/devices/${encodeURIComponent(deviceId)}/quarantine`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: 'Manual quarantine from dashboard' }),
            });
            showFeedback(`Device ${deviceId} quarantined`, 'info');
        } else if (action === 'authorize') {
            await fetchJSON(`/api/devices/${encodeURIComponent(deviceId)}/authorize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: 'Manual authorization from dashboard' }),
            });
            showFeedback(`Device ${deviceId} authorized`, 'success');
        } else if (action === 'delete') {
            await fetchJSON(`/api/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' });
            showFeedback(`Device ${deviceId} deleted`, 'info');
        }
        refreshDevices();
    } catch (err) {
        console.error(`Action ${action} failed`, err);
        showFeedback(err.message, 'error');
    }
});

async function init() {
    try {
        await Promise.all([refreshMetrics(), refreshDevices(), initialiseAlerts()]);
        subscribeToAlerts();
        startAutoRefresh();
    } catch (err) {
        console.error('Failed to initialise dashboard', err);
        showFeedback('Failed to initialise dashboard. Check logs.', 'error');
    }
}

metricSelect.addEventListener('change', () => updateChart().catch(console.error));
machineSelect.addEventListener('change', () => updateChart().catch(console.error));

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        refreshMetrics();
        refreshDevices();
        startAutoRefresh();
    }
});

document.addEventListener('DOMContentLoaded', init);
