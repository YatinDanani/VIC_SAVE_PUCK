"""Flask application factory and SocketIO initialization."""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app(skip_ai: bool = False, debug: bool = False) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = "vic-save-puck-demo"
    app.config["SKIP_AI"] = skip_ai

    # Register routes
    from vic_save_puck.web.routes import bp
    app.register_blueprint(bp)

    # Import events to register SocketIO handlers
    from vic_save_puck.web import events  # noqa: F401

    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    return app
