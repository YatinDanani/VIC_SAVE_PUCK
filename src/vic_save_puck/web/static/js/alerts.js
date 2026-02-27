/* AI alert feed */

const Alerts = {
    count: 0,

    reset() {
        this.count = 0;
        document.getElementById('alert-count').textContent = '0';
        document.getElementById('alert-feed').innerHTML =
            '<div class="alert-placeholder">AI alerts will appear here when drift is detected</div>';
    },

    addAlert(data) {
        this.count++;
        document.getElementById('alert-count').textContent = String(this.count);

        const feed = document.getElementById('alert-feed');
        // Remove placeholder
        const placeholder = feed.querySelector('.alert-placeholder');
        if (placeholder) placeholder.remove();

        const item = document.createElement('div');
        item.className = `alert-item ${data.cause || 'noise'}`;

        const actionsHtml = (data.actions || []).map(a =>
            `${a.stand || 'ALL'}: ${a.action} ${a.item || ''} (${a.quantity_change_pct > 0 ? '+' : ''}${a.quantity_change_pct || 0}%)`
        ).join('<br>');

        item.innerHTML = `
            <div class="alert-header">
                <span class="alert-cause">${data.cause || 'unknown'}</span>
                <span class="alert-confidence">T+${data.time_window}min · ${((data.confidence || 0) * 100).toFixed(0)}% conf</span>
            </div>
            <div class="alert-text">${data.alert_text || ''}</div>
            ${actionsHtml ? `<div class="alert-actions">${actionsHtml}</div>` : ''}
        `;

        // Insert at top (newest first)
        feed.insertBefore(item, feed.firstChild);
    },
};
