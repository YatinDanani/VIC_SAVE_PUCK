/* Global state and SocketIO connection */

const App = {
    socket: null,
    state: {
        connected: false,
        running: false,
        scenario: null,
        gameInfo: null,
        forecastSummary: null,
        currentWindow: null,
        windowCount: 0,
        totalWindows: 0,
    },

    init() {
        this.socket = io();

        this.socket.on('connect', () => {
            this.state.connected = true;
            document.getElementById('connection-status').className = 'status-dot connected';
            document.getElementById('connection-status').title = 'Connected';
        });

        this.socket.on('disconnect', () => {
            this.state.connected = false;
            document.getElementById('connection-status').className = 'status-dot disconnected';
            document.getElementById('connection-status').title = 'Disconnected';
        });

        this.socket.on('sim:status', (data) => {
            this.showToast(data.message, 'info');
        });

        this.socket.on('sim:started', (data) => {
            this.state.running = true;
            this.state.scenario = data.scenario;
            this.state.gameInfo = data.game_info;
            this.state.forecastSummary = data.forecast_summary;
            this.state.windowCount = 0;

            // Update header
            const badge = document.getElementById('scenario-badge');
            badge.textContent = data.scenario.name;
            badge.classList.remove('hidden');

            const infoBadge = document.getElementById('game-info-badge');
            infoBadge.textContent = `vs ${data.game_info.opponent} | ${data.game_info.attendance.toLocaleString()} fans | ${data.game_info.archetype}`;
            infoBadge.classList.remove('hidden');

            // Reset UI
            Charts.reset(data.forecast_summary);
            Traffic.reset();
            Alerts.reset();
            document.getElementById('post-game-card').classList.add('hidden');

            Controls.onSimStarted();
        });

        this.socket.on('sim:window', (data) => {
            this.state.currentWindow = data.time_window;
            this.state.windowCount = data.window_index + 1;
            this.state.totalWindows = data.total_windows;

            // Update game clock
            this.updateClock(data.time_window);

            // Update charts
            Charts.addWindow(data);

            // Update drift badges
            this.updateDriftBadge('overall-drift', data.drift_pct);
            this.updateDriftBadge('cumulative-drift', data.cumulative_drift);
        });

        this.socket.on('sim:traffic', (data) => {
            Traffic.update(data);
        });

        this.socket.on('sim:alert', (data) => {
            Alerts.addAlert(data);
        });

        this.socket.on('sim:complete', (data) => {
            this.state.running = false;
            Controls.onSimStopped();
            this.showPostGame(data);
            this.showToast('Game simulation complete!', 'success');
        });

        this.socket.on('sim:error', (data) => {
            this.state.running = false;
            Controls.onSimStopped();
            this.showToast(`Error: ${data.message}`, 'error');
        });

        this.socket.on('sim:override_applied', (data) => {
            this.showToast(`Override applied: ${data.type} at T+${data.applied_at_window}min`, 'success');
            Charts.addAnnotation(data.applied_at_window, data.type);
        });

        // Init all modules
        Charts.init();
        Controls.init();
    },

    updateClock(timeWindow) {
        const clock = document.getElementById('game-clock');
        const prefix = timeWindow >= 0 ? '+' : '';
        let period = '';
        if (timeWindow < 0) period = 'PRE';
        else if (timeWindow < 20) period = 'P1';
        else if (timeWindow < 38) period = 'INT1';
        else if (timeWindow < 58) period = 'P2';
        else if (timeWindow < 76) period = 'INT2';
        else if (timeWindow < 96) period = 'P3';
        else period = 'POST';

        clock.textContent = `T${prefix}${timeWindow}min · ${period}`;
    },

    updateDriftBadge(id, drift) {
        const el = document.getElementById(id);
        const pct = (drift * 100).toFixed(1);
        const sign = drift >= 0 ? '+' : '';
        el.textContent = `${sign}${pct}%`;
        el.className = 'drift-badge';
        if (Math.abs(drift) <= 0.15) el.classList.add('green');
        else if (Math.abs(drift) <= 0.30) el.classList.add('yellow');
        else el.classList.add('red');
    },

    showPostGame(data) {
        const card = document.getElementById('post-game-card');
        const content = document.getElementById('post-game-content');

        const s = data.summary;
        let html = '<div class="summary-grid">';
        html += `<div class="summary-item"><div class="summary-label">Total Forecast</div><div class="summary-value">${(s.total_forecast || 0).toLocaleString()}</div></div>`;
        html += `<div class="summary-item"><div class="summary-label">Total Actual</div><div class="summary-value">${(s.total_actual || 0).toLocaleString()}</div></div>`;
        html += `<div class="summary-item"><div class="summary-label">Cumulative Drift</div><div class="summary-value">${s.cumulative_drift || '0%'}</div></div>`;
        html += `<div class="summary-item"><div class="summary-label">Drift Windows</div><div class="summary-value">${s.windows_with_drift || 0}/${s.total_windows || 0}</div></div>`;
        html += `<div class="summary-item"><div class="summary-label">Critical Signals</div><div class="summary-value">${s.critical_signals || 0}</div></div>`;
        html += `<div class="summary-item"><div class="summary-label">AI Alerts</div><div class="summary-value">${data.total_alerts || 0}</div></div>`;
        html += '</div>';

        if (data.post_game_report) {
            html += `<div style="border-top: 1px solid var(--border); padding-top: 12px; margin-top: 8px;">${data.post_game_report}</div>`;
        }

        content.innerHTML = html;
        card.classList.remove('hidden');
    },

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
