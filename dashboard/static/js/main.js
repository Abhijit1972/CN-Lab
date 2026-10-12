// Global Chart.js settings for Dark Theme
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.scale.grid.color = 'rgba(51, 65, 85, 0.5)';

// Setup Charts
const ctxThroughput = document.getElementById('throughputChart').getContext('2d');
const throughputChart = new Chart(ctxThroughput, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {
                label: 'Throughput (KB/s)',
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                data: [],
                tension: 0.3
            },
            {
                label: 'Threshold',
                borderColor: '#f59e0b',
                borderWidth: 1.5,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false,
                data: [],
                stepped: true
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: { display: false },
            y: { beginAtZero: true }
        },
        plugins: {
            legend: { display: true, position: 'top' }
        }
    }
});

const ctxRate = document.getElementById('rateChart').getContext('2d');
const rateChart = new Chart(ctxRate, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {
                label: 'Packet Rate (pkt/s)',
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                data: [],
                tension: 0.3
            },
            {
                label: 'Threshold',
                borderColor: '#f59e0b',
                borderWidth: 1.5,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false,
                data: [],
                stepped: true
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: { x: { display: false }, y: { beginAtZero: true } }
    }
});

const ctxRetx = document.getElementById('retxChart').getContext('2d');
const retxChart = new Chart(ctxRetx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {
                label: 'Retransmission Ratio',
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                fill: true,
                data: [],
                tension: 0.3
            },
            {
                label: 'Threshold',
                borderColor: '#f59e0b',
                borderWidth: 1.5,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false,
                data: [],
                stepped: true
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: { x: { display: false }, y: { beginAtZero: true } }
    }
});

const ctxProtocol = document.getElementById('protocolChart').getContext('2d');
const protocolChart = new Chart(ctxProtocol, {
    type: 'doughnut',
    data: {
        labels: ['TCP', 'UDP', 'ICMP', 'Other'],
        datasets: [{
            data: [0, 0, 0, 0],
            backgroundColor: [
                '#3b82f6', // TCP
                '#10b981', // UDP
                '#f59e0b', // ICMP
                '#64748b'  // Other
            ],
            borderWidth: 0,
            hoverOffset: 4
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { position: 'right' }
        },
        cutout: '70%'
    }
});

// Update DOM elements
function updateStatusBadge(level) {
    const badge = document.getElementById('current-status');
    const indicator = document.getElementById('live-indicator');
    
    badge.textContent = level;
    badge.className = 'status-badge badge-' + level.toLowerCase();
    
    // Change dot color based on status
    const colors = {
        'WARMUP': '#0ea5e9',
        'NORMAL': '#10b981',
        'WARNING': '#f59e0b',
        'CONGESTED': '#ef4444'
    };
    indicator.style.backgroundColor = colors[level] || colors['NORMAL'];
    indicator.style.boxShadow = `0 0 10px ${colors[level] || colors['NORMAL']}`;
}

function updateSummaryCards(summary) {
    document.getElementById('val-active-windows').textContent = summary.active_windows;
    document.getElementById('val-avg-bw').textContent = summary.avg_throughput_kbps.toFixed(1);
    document.getElementById('val-peak-bw').textContent = summary.peak_throughput_kbps.toFixed(1);
    document.getElementById('val-events').textContent = summary.congestion_events;
    document.getElementById('val-event-time').textContent = summary.total_congestion_s;
}

function updateAlertsTable(alerts) {
    const tbody = document.querySelector('#alerts-table tbody');
    tbody.innerHTML = '';
    
    if (alerts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No recent alerts</td></tr>';
        return;
    }
    
    alerts.forEach(alert => {
        const tr = document.createElement('tr');
        const timeParts = alert.time.split('T');
        const timeStr = timeParts.length > 1 ? timeParts[1] : alert.time;
        
        tr.innerHTML = `
            <td>${timeStr}</td>
            <td><span class="tag tag-${alert.level.toLowerCase()}">${alert.level}</span></td>
            <td style="color: var(--status-warning);">${alert.params_over.join(', ')}</td>
            <td>${alert.throughput.toFixed(1)}</td>
            <td>${alert.packet_rate.toFixed(0)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateCharts(history) {
    const labels = [];
    const bwData = [], bwThresh = [];
    const rateData = [], rateThresh = [];
    const retxData = [], retxThresh = [];
    
    // Default to 0 for protocol doughnut if history is empty
    let lastTcp = 0, lastUdp = 0, lastIcmp = 0, lastOther = 0;
    
    history.forEach(row => {
        const timeParts = row.timestamp.split('T');
        labels.push(timeParts.length > 1 ? timeParts[1] : row.timestamp);
        
        bwData.push(row.throughput_kbps);
        bwThresh.push(row.T_throughput);
        
        rateData.push(row.packet_rate);
        rateThresh.push(row.T_rate);
        
        retxData.push(row.retx_ratio);
        retxThresh.push(row.T_retx);
        
        lastTcp = row.tcp_pct;
        lastUdp = row.udp_pct;
        lastIcmp = row.icmp_pct;
        lastOther = row.other_pct;
    });

    // Update Line Charts
    throughputChart.data.labels = labels;
    throughputChart.data.datasets[0].data = bwData;
    throughputChart.data.datasets[1].data = bwThresh;
    throughputChart.update();
    
    rateChart.data.labels = labels;
    rateChart.data.datasets[0].data = rateData;
    rateChart.data.datasets[1].data = rateThresh;
    rateChart.update();
    
    retxChart.data.labels = labels;
    retxChart.data.datasets[0].data = retxData;
    retxChart.data.datasets[1].data = retxThresh;
    retxChart.update();
    
    // Update Protocol Chart
    protocolChart.data.datasets[0].data = [lastTcp, lastUdp, lastIcmp, lastOther];
    protocolChart.update();
    
    // Update live text values
    if (history.length > 0) {
        const last = history[history.length - 1];
        document.getElementById('live-throughput').textContent = last.throughput_kbps.toFixed(1);
        document.getElementById('live-rate').textContent = Math.round(last.packet_rate);
        document.getElementById('live-retx').textContent = last.retx_ratio.toFixed(3);
    }
}

// Polling loop
async function pollData() {
    try {
        // Fetch data concurrently
        const [statusRes, summaryRes, alertsRes, historyRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/summary'),
            fetch('/api/alerts'),
            fetch('/api/history')
        ]);
        
        const status = await statusRes.json();
        const summary = await summaryRes.json();
        const alerts = await alertsRes.json();
        const history = await historyRes.json();
        
        if (status.level) updateStatusBadge(status.level);
        updateSummaryCards(summary);
        updateAlertsTable(alerts);
        updateCharts(history);
        
    } catch (err) {
        console.error("Error fetching dashboard data:", err);
        // Optional: show offline status
    }
    
    // Schedule next poll
    setTimeout(pollData, 1000);
}

// Start polling
pollData();
