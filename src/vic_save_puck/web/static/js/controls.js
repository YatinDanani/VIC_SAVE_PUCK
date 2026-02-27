/* Controls: scenario picker, speed slider, start/stop, inject forms */

const Controls = {
    init() {
        this._loadScenarios();
        this._bindSpeedSlider();
        this._bindButtons();
        this._bindInjectForms();
    },

    async _loadScenarios() {
        try {
            const res = await fetch('/api/scenarios');
            const scenarios = await res.json();
            const select = document.getElementById('scenario-select');
            select.innerHTML = '';
            for (const s of scenarios) {
                const opt = document.createElement('option');
                opt.value = s.key;
                opt.textContent = `${s.name} — ${s.description}`;
                select.appendChild(opt);
            }
        } catch (e) {
            console.error('Failed to load scenarios:', e);
        }
    },

    _bindSpeedSlider() {
        const slider = document.getElementById('speed-slider');
        const display = document.getElementById('speed-value');
        slider.addEventListener('input', () => {
            display.textContent = slider.value;
            // Update speed on live sim
            if (App.state.running) {
                App.socket.emit('sim:speed', { speed: parseFloat(slider.value) });
            }
        });

        // Spike factor slider
        const spikeSlider = document.getElementById('spike-factor');
        const spikeDisplay = document.getElementById('spike-factor-value');
        spikeSlider.addEventListener('input', () => {
            spikeDisplay.textContent = parseFloat(spikeSlider.value).toFixed(1);
        });

        // Volume factor slider
        const volSlider = document.getElementById('volume-factor');
        const volDisplay = document.getElementById('volume-factor-value');
        volSlider.addEventListener('input', () => {
            volDisplay.textContent = parseFloat(volSlider.value).toFixed(1);
        });
    },

    _bindButtons() {
        document.getElementById('btn-start').addEventListener('click', () => {
            const scenario = document.getElementById('scenario-select').value;
            const speed = parseFloat(document.getElementById('speed-slider').value);
            const skipAi = document.getElementById('skip-ai-toggle').checked;

            App.socket.emit('sim:start', { scenario, speed, skip_ai: skipAi });
        });

        document.getElementById('btn-stop').addEventListener('click', () => {
            App.socket.emit('sim:stop', {});
            App.state.running = false;
            this.onSimStopped();
        });
    },

    _bindInjectForms() {
        // Toggle outage form
        document.getElementById('btn-inject-outage').addEventListener('click', () => {
            document.getElementById('outage-form').classList.toggle('hidden');
        });

        // Toggle spike form
        document.getElementById('btn-inject-spike').addEventListener('click', () => {
            document.getElementById('spike-form').classList.toggle('hidden');
        });

        // Confirm outage
        document.getElementById('btn-confirm-outage').addEventListener('click', () => {
            const stand = document.getElementById('outage-stand').value;
            const duration = parseInt(document.getElementById('outage-duration').value) || 20;
            const startMin = App.state.currentWindow || 0;
            App.socket.emit('sim:inject', {
                type: 'stand_outage',
                params: { stand, start_min: startMin, end_min: startMin + duration }
            });
            document.getElementById('outage-form').classList.add('hidden');
        });

        // Confirm spike
        document.getElementById('btn-confirm-spike').addEventListener('click', () => {
            const stand = document.getElementById('spike-stand').value;
            const factor = parseFloat(document.getElementById('spike-factor').value);
            const afterMin = App.state.currentWindow || 0;
            App.socket.emit('sim:inject', {
                type: 'demand_spike',
                params: { stand, factor, after_min: afterMin }
            });
            document.getElementById('spike-form').classList.add('hidden');
        });

        // Confirm volume
        document.getElementById('btn-confirm-volume').addEventListener('click', () => {
            const factor = parseFloat(document.getElementById('volume-factor').value);
            App.socket.emit('sim:inject', {
                type: 'global_volume',
                params: { factor }
            });
        });
    },

    onSimStarted() {
        document.getElementById('btn-start').disabled = true;
        document.getElementById('btn-stop').disabled = false;
        document.getElementById('scenario-select').disabled = true;
        document.getElementById('btn-inject-outage').disabled = false;
        document.getElementById('btn-inject-spike').disabled = false;
        document.getElementById('volume-factor').disabled = false;
        document.getElementById('btn-confirm-volume').disabled = false;
    },

    onSimStopped() {
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-stop').disabled = true;
        document.getElementById('scenario-select').disabled = false;
        document.getElementById('btn-inject-outage').disabled = true;
        document.getElementById('btn-inject-spike').disabled = true;
        document.getElementById('volume-factor').disabled = true;
        document.getElementById('btn-confirm-volume').disabled = true;
        document.getElementById('game-clock').textContent = 'FINAL';
    },
};
