"""Real-time traffic light system: Green/Yellow/Red prediction vs actual status."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from vic_save_puck.config import STAND_SHORT
from vic_save_puck.models.drift import DriftDetector, DriftReport
from vic_save_puck.simulator.engine import GameEvent


class Status(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

    @property
    def emoji(self) -> str:
        return {"green": "🟢", "yellow": "🟡", "red": "🔴"}[self.value]

    @property
    def label(self) -> str:
        return {"green": "ON TRACK", "yellow": "WATCH", "red": "ACTION"}[self.value]


# Thresholds
GREEN_THRESHOLD = 0.15    # ±15%
YELLOW_THRESHOLD = 0.30   # ±30%


@dataclass
class StandStatus:
    """Current status for a single stand."""
    stand: str
    status: Status
    drift_pct: float
    forecast_qty: int
    actual_qty: int
    trend: str  # "improving", "stable", "worsening"

    @property
    def short_name(self) -> str:
        return STAND_SHORT.get(self.stand, self.stand)

    def __str__(self) -> str:
        return (
            f"{self.status.emoji} {self.short_name:<18} | "
            f"{self.drift_pct:+6.0%} | "
            f"F:{self.forecast_qty:>4} A:{self.actual_qty:>4} | "
            f"{self.trend}"
        )


@dataclass
class OverallStatus:
    """Overall game status at a point in time."""
    time_window: int
    overall_status: Status
    overall_drift: float
    stand_statuses: list[StandStatus]
    cumulative_drift: float

    def __str__(self) -> str:
        lines = [
            f"T{self.time_window:+4}min | {self.overall_status.emoji} {self.overall_status.label} | "
            f"Overall: {self.overall_drift:+.0%} | Cumulative: {self.cumulative_drift:+.0%}",
        ]
        for ss in self.stand_statuses:
            lines.append(f"  {ss}")
        return "\n".join(lines)


def classify_status(drift: float) -> Status:
    """Classify a drift value into a traffic light status."""
    abs_drift = abs(drift)
    if abs_drift <= GREEN_THRESHOLD:
        return Status.GREEN
    elif abs_drift <= YELLOW_THRESHOLD:
        return Status.YELLOW
    else:
        return Status.RED


class TrafficLightMonitor:
    """
    Maintains real-time traffic light status for the game.

    Tracks per-stand and overall status, including trend detection
    (improving/worsening over recent windows).
    """

    def __init__(self, detector: DriftDetector):
        self.detector = detector
        self._history: list[OverallStatus] = []
        self._stand_drift_history: dict[str, list[float]] = {}

    def update(self, time_window: int) -> OverallStatus:
        """Compute current status after a drift check."""
        # Get the latest report
        report = None
        for r in reversed(self.detector.history):
            if r.time_window == time_window:
                report = r
                break

        if report is None:
            return OverallStatus(
                time_window=time_window,
                overall_status=Status.GREEN,
                overall_drift=0.0,
                stand_statuses=[],
                cumulative_drift=self.detector.cumulative_drift(),
            )

        # Overall status
        overall_drift = report.overall_volume_drift
        overall_status = classify_status(overall_drift)
        cumulative = self.detector.cumulative_drift()

        # Per-stand statuses
        stand_statuses = []
        for stand, drift in report.stand_drifts.items():
            # Track history for trend
            if stand not in self._stand_drift_history:
                self._stand_drift_history[stand] = []
            self._stand_drift_history[stand].append(drift)

            trend = self._compute_trend(self._stand_drift_history[stand])

            # Get forecast and actual for this stand+window
            fc_key = (stand, time_window)
            fc_qty = self.detector._fc_stand.get(fc_key, 0)
            actual_qty = self.detector._actual_by_stand_window.get(fc_key, 0)

            stand_statuses.append(StandStatus(
                stand=stand,
                status=classify_status(drift),
                drift_pct=drift,
                forecast_qty=fc_qty,
                actual_qty=actual_qty,
                trend=trend,
            ))

        # Sort: red first, then yellow, then green
        priority = {Status.RED: 0, Status.YELLOW: 1, Status.GREEN: 2}
        stand_statuses.sort(key=lambda s: (priority[s.status], -abs(s.drift_pct)))

        status = OverallStatus(
            time_window=time_window,
            overall_status=overall_status,
            overall_drift=overall_drift,
            stand_statuses=stand_statuses,
            cumulative_drift=cumulative,
        )
        self._history.append(status)
        return status

    def _compute_trend(self, history: list[float]) -> str:
        """Determine if drift is improving, stable, or worsening."""
        if len(history) < 2:
            return "stable"

        recent = history[-3:] if len(history) >= 3 else history
        # Compare absolute drift: is it getting closer to 0 or further?
        if len(recent) >= 2:
            recent_abs = [abs(d) for d in recent]
            if recent_abs[-1] < recent_abs[0] - 0.05:
                return "improving"
            elif recent_abs[-1] > recent_abs[0] + 0.05:
                return "worsening"
        return "stable"

    @property
    def current_status(self) -> Status:
        """Get the worst current status across all stands."""
        if not self._history:
            return Status.GREEN
        latest = self._history[-1]
        if any(s.status == Status.RED for s in latest.stand_statuses):
            return Status.RED
        if any(s.status == Status.YELLOW for s in latest.stand_statuses):
            return Status.YELLOW
        return Status.GREEN

    def summary_line(self) -> str:
        """One-line summary of current state."""
        if not self._history:
            return "No data yet"
        latest = self._history[-1]
        red = sum(1 for s in latest.stand_statuses if s.status == Status.RED)
        yellow = sum(1 for s in latest.stand_statuses if s.status == Status.YELLOW)
        green = sum(1 for s in latest.stand_statuses if s.status == Status.GREEN)
        # Only show cumulative drift once enough data has accumulated
        cum_str = ""
        if self.detector._cumulative_forecast > 500:
            cum_str = f" (cum: {latest.cumulative_drift:+.0%})"
        return (
            f"{latest.overall_status.emoji} T{latest.time_window:+}min | "
            f"🔴{red} 🟡{yellow} 🟢{green} | "
            f"Drift: {latest.overall_drift:+.0%}{cum_str}"
        )
