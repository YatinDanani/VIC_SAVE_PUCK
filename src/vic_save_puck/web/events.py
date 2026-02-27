"""SocketIO event handlers."""

from __future__ import annotations

from flask import current_app
from flask_socketio import emit

from vic_save_puck.web.app import socketio
from vic_save_puck.web.simulation import WebSimulation

# Track the active simulation (one at a time)
_active_sim: WebSimulation | None = None


@socketio.on("connect")
def handle_connect():
    emit("sim:status", {"message": "Connected to VIC SAVE PUCK server"})


@socketio.on("sim:start")
def handle_start(data):
    global _active_sim

    # Stop any existing simulation
    if _active_sim is not None:
        _active_sim.stop()

    scenario = data.get("scenario", "normal")
    speed = float(data.get("speed", 60))
    skip_ai = data.get("skip_ai", current_app.config.get("SKIP_AI", False))

    _active_sim = WebSimulation(
        socketio=socketio,
        scenario_key=scenario,
        speed=speed,
        skip_ai=skip_ai,
    )
    _active_sim.start()


@socketio.on("sim:stop")
def handle_stop(data=None):
    global _active_sim
    if _active_sim is not None:
        _active_sim.stop()
        _active_sim = None
    emit("sim:status", {"message": "Simulation stopped"})


@socketio.on("sim:speed")
def handle_speed(data):
    global _active_sim
    if _active_sim is not None:
        speed = float(data.get("speed", 60))
        _active_sim.update_speed(speed)
        emit("sim:status", {"message": f"Speed updated to {speed}x"})


@socketio.on("sim:inject")
def handle_inject(data):
    global _active_sim
    if _active_sim is not None:
        override_type = data.get("type", "")
        params = data.get("params", {})
        _active_sim.inject_override(override_type, params)
    else:
        emit("sim:error", {"message": "No active simulation"})
