"""HTTP routes for the web dashboard."""

from __future__ import annotations

from flask import Blueprint, render_template, jsonify, current_app

from vic_save_puck.simulator.scenarios import list_scenarios
from vic_save_puck.config import STAND_SHORT

bp = Blueprint("main", __name__)


@bp.route("/")
def dashboard():
    return render_template("dashboard.html")


@bp.route("/api/scenarios")
def api_scenarios():
    return jsonify(list_scenarios())


@bp.route("/api/stands")
def api_stands():
    return jsonify([
        {"full": full, "short": short}
        for full, short in STAND_SHORT.items()
    ])
