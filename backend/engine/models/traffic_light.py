"""Real-time traffic light system: Green/Yellow/Red prediction vs actual status."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from engine.config import STAND_SHORT
from engine.models.drift import DriftDetector, DriftReport
from engine.simulator.engine import GameEvent


class Status(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


GREEN_THRESHOLD = 0.15
YELLOW_THRESHOLD = 0.30


@dataclass
class StandStatus:
    stand: str
    status: Status
    drift_pct: float
    forecast_qty: int
    actual_qty: int
    trend: str

    @property
    def short_name(self) -> str:
        return STAND_SHORT.get(self.stand, self.stand)

    def to_dict(self) -> dict:
        return {
            "stand": self.short_name,
            "status": self.status.value,
            "drift_pct": round(self.drift_pct, 3),
            "forecast_qty": self.forecast_qty,
            "actual_qty": self.actual_qty,
            "trend": self.trend,
        }


@dataclass
class OverallStatus:
    time_window: int
    overall_status: Status
    overall_drift: float
    stand_statuses: list[StandStatus]
    cumulative_drift: float

    def to_dict(self) -> dict:
        return {
            "time_window": self.time_window,
            "overall_status": self.overall_status.value,
            "overall_drift": round(self.overall_drift, 3),
            "cumulative_drift": round(self.cumulative_drift, 3),
            "stands": [s.to_dict() for s in self.stand_statuses],
        }


def classify_status(drift: float) -> Status:
    abs_drift = abs(drift)
    if abs_drift <= GREEN_THRESHOLD:
        return Status.GREEN
    elif abs_drift <= YELLOW_THRESHOLD:
        return Status.YELLOW
    else:
        return Status.RED


class TrafficLightMonitor:
    def __init__(self, detector: DriftDetector):
        self.detector = detector
        self._history: list[OverallStatus] = []
        self._stand_drift_history: dict[str, list[float]] = {}

    def update(self, time_window: int) -> OverallStatus:
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

        overall_drift = report.overall_volume_drift
        overall_status = classify_status(overall_drift)
        cumulative = self.detector.cumulative_drift()

        stand_statuses = []
        for stand, drift in report.stand_drifts.items():
            if stand not in self._stand_drift_history:
                self._stand_drift_history[stand] = []
            self._stand_drift_history[stand].append(drift)

            trend = self._compute_trend(self._stand_drift_history[stand])

            fc_key = (stand, time_window)
            fc_qty = self.detector._fc_stand.get(fc_key, 0)
            actual_qty = self.detector._actual_by_stand_window.get(fc_key, 0)

            stand_statuses.append(StandStatus(
                stand=stand, status=classify_status(drift),
                drift_pct=drift, forecast_qty=fc_qty,
                actual_qty=actual_qty, trend=trend,
            ))

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
        if len(history) < 2:
            return "stable"
        recent = history[-3:] if len(history) >= 3 else history
        if len(recent) >= 2:
            recent_abs = [abs(d) for d in recent]
            if recent_abs[-1] < recent_abs[0] - 0.05:
                return "improving"
            elif recent_abs[-1] > recent_abs[0] + 0.05:
                return "worsening"
        return "stable"

    @property
    def current_status(self) -> Status:
        if not self._history:
            return Status.GREEN
        latest = self._history[-1]
        if any(s.status == Status.RED for s in latest.stand_statuses):
            return Status.RED
        if any(s.status == Status.YELLOW for s in latest.stand_statuses):
            return Status.YELLOW
        return Status.GREEN
