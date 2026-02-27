"""Background simulation thread that bridges the simulator to WebSocket events."""

from __future__ import annotations

import threading
import time
import traceback

from vic_save_puck.data.profiles import build_profiles
from vic_save_puck.models.forecast import forecast_for_game
from vic_save_puck.models.prep_plan import generate_prep_plan
from vic_save_puck.models.drift import DriftDetector
from vic_save_puck.models.traffic_light import TrafficLightMonitor, Status
from vic_save_puck.simulator.engine import GameEvent, NoiseConfig
from vic_save_puck.simulator.scenarios import get_scenarios
from vic_save_puck.ai.reasoning import analyze_drift, ReasoningResult
from vic_save_puck.ai.post_game import generate_post_game_report
from vic_save_puck.web.serializers import (
    serialize_drift_report,
    serialize_overall_status,
    serialize_reasoning_result,
    serialize_forecast_summary,
)


class WebSimulation:
    """Runs a game simulation in a background thread, emitting SocketIO events."""

    def __init__(self, socketio, scenario_key: str, speed: float, skip_ai: bool):
        self.socketio = socketio
        self.scenario_key = scenario_key
        self.speed = speed
        self.skip_ai = skip_ai

        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._noise_overrides: list[dict] = []
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._running = False

    def update_speed(self, speed: float):
        with self._lock:
            self.speed = max(1.0, min(500.0, speed))

    def inject_override(self, override_type: str, params: dict):
        with self._lock:
            self._noise_overrides.append({"type": override_type, "params": params})

    def _emit(self, event: str, data: dict):
        self.socketio.emit(event, data)

    def _run(self):
        try:
            self._emit("sim:status", {"message": "Loading historical profiles..."})

            profiles = build_profiles()

            scenarios = get_scenarios()
            if self.scenario_key not in scenarios:
                self._emit("sim:error", {"message": f"Unknown scenario: {self.scenario_key}"})
                self._running = False
                return

            scenario = scenarios[self.scenario_key]

            self._emit("sim:status", {"message": "Generating forecast..."})
            forecast = forecast_for_game(scenario.game_date, profiles=profiles)
            prep_actions = generate_prep_plan(forecast)

            # Build simulator and run batch
            sim = scenario.build_simulator(speed=self.speed)
            game_info = sim.game_info

            self._emit("sim:started", {
                "scenario": {
                    "key": self.scenario_key,
                    "name": scenario.name,
                    "description": scenario.description,
                },
                "game_info": game_info,
                "forecast_summary": serialize_forecast_summary(forecast),
                "prep_actions_count": len(prep_actions),
            })

            if self._stop.is_set():
                self._running = False
                return

            self._emit("sim:status", {"message": "Running simulation..."})
            all_events = sim.run_batch()

            # Group events by time window
            window_buffers: dict[int, list[GameEvent]] = {}
            for event in all_events:
                tw = event.time_window
                if tw not in window_buffers:
                    window_buffers[tw] = []
                window_buffers[tw].append(event)

            # Initialize drift detection
            detector = DriftDetector(forecast)
            traffic_monitor = TrafficLightMonitor(detector)
            reasoning_results: list[ReasoningResult] = []
            sorted_windows = sorted(window_buffers.keys())

            # Process window by window
            for i, tw in enumerate(sorted_windows):
                if self._stop.is_set():
                    break

                # Check for overrides
                self._apply_overrides(sim, tw)

                # Ingest all events for this window
                window_events = window_buffers[tw]
                for event in window_events:
                    detector.ingest_event(event)

                # Check drift and traffic status
                report = detector.check_drift(tw)
                status = traffic_monitor.update(tw)

                actual_qty = sum(e.qty for e in window_events)
                fc_qty = sum(
                    v for (s, t), v in detector._fc_stand.items() if t == tw
                )

                # Emit window data
                self._emit("sim:window", {
                    "time_window": tw,
                    "window_index": i,
                    "total_windows": len(sorted_windows),
                    "actual_qty": actual_qty,
                    "forecast_qty": fc_qty,
                    "drift_pct": round(report.overall_volume_drift, 3),
                    "cumulative_drift": round(detector.cumulative_drift(), 3),
                    "event_count": len(window_events),
                    "drift_report": serialize_drift_report(report),
                })

                # Emit traffic light data
                self._emit("sim:traffic", serialize_overall_status(status))

                # AI reasoning for RED status
                if not self.skip_ai and status.overall_status == Status.RED:
                    try:
                        result = analyze_drift(
                            drift_report=report,
                            game_context=game_info,
                            cumulative_drift=detector.cumulative_drift(),
                            recent_reports=detector.history[-5:],
                        )
                        reasoning_results.append(result)
                        self._emit("sim:alert", {
                            "time_window": tw,
                            **serialize_reasoning_result(result),
                        })
                    except Exception:
                        pass

                # Sleep between windows for pacing
                with self._lock:
                    current_speed = self.speed
                delay = 10.0 / current_speed
                # Use small sleep intervals so we can check stop flag
                elapsed = 0.0
                while elapsed < delay and not self._stop.is_set():
                    step = min(0.1, delay - elapsed)
                    time.sleep(step)
                    elapsed += step

            # Game complete
            if not self._stop.is_set():
                summary = detector.summary()

                post_game_text = None
                if not self.skip_ai:
                    try:
                        post_game_text = generate_post_game_report(
                            game_context=game_info,
                            drift_detector=detector,
                            reasoning_results=reasoning_results,
                            forecast=forecast,
                        )
                    except Exception:
                        pass

                self._emit("sim:complete", {
                    "summary": summary,
                    "post_game_report": post_game_text,
                    "total_alerts": len(reasoning_results),
                })

        except Exception as e:
            self._emit("sim:error", {
                "message": str(e),
                "traceback": traceback.format_exc(),
            })
        finally:
            self._running = False

    def _apply_overrides(self, sim, current_window: int):
        """Apply any queued noise overrides to the simulator."""
        with self._lock:
            overrides = self._noise_overrides[:]
            self._noise_overrides.clear()

        for override in overrides:
            otype = override["type"]
            params = override["params"]

            if otype == "stand_outage":
                sim.noise.stand_outage = params.get("stand")
                sim.noise.stand_outage_start_min = float(params.get("start_min", current_window))
                sim.noise.stand_outage_end_min = float(params.get("end_min", current_window + 30))
            elif otype == "demand_spike":
                sim.noise.demand_spike_stand = params.get("stand")
                sim.noise.demand_spike_factor = float(params.get("factor", 2.0))
                sim.noise.demand_spike_after_min = float(params.get("after_min", current_window))
            elif otype == "global_volume":
                sim.noise.global_volume_factor = float(params.get("factor", 1.0))

            self._emit("sim:override_applied", {
                "type": otype,
                "params": params,
                "applied_at_window": current_window,
            })
