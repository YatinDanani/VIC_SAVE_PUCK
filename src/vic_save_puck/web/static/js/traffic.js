/* Traffic light grid — stand status cards */

const Traffic = {
    reset() {
        const grid = document.getElementById('traffic-grid');
        grid.innerHTML = '<div class="traffic-placeholder">Waiting for simulation data...</div>';
    },

    update(data) {
        const grid = document.getElementById('traffic-grid');
        const stands = data.stands || [];

        if (stands.length === 0) return;

        grid.innerHTML = '';

        for (const stand of stands) {
            const card = document.createElement('div');
            card.className = `stand-card ${stand.status}`;

            const driftPct = (stand.drift_pct * 100).toFixed(1);
            const sign = stand.drift_pct >= 0 ? '+' : '';
            const driftClass = Math.abs(stand.drift_pct) <= 0.15 ? 'neutral' :
                              (stand.drift_pct > 0 ? 'positive' : 'negative');

            const statusEmoji = { green: '🟢', yellow: '🟡', red: '🔴' }[stand.status] || '⚪';
            const trendArrow = { improving: '↗ improving', worsening: '↘ worsening', stable: '→ stable' }[stand.trend] || '';

            card.innerHTML = `
                <div class="stand-name">${statusEmoji} ${stand.short_name}</div>
                <div class="stand-drift ${driftClass}">${sign}${driftPct}%</div>
                <div class="stand-details">F:${stand.forecast_qty} → A:${stand.actual_qty}</div>
                <div class="stand-trend ${stand.trend}">${trendArrow}</div>
            `;

            grid.appendChild(card);
        }
    },
};
