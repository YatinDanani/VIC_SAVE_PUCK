"""Real-time drift detection: compare streaming actuals to forecast."""

from __future__ import annotations

from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from engine.config import (
    DRIFT_VOLUME_THRESHOLD, DRIFT_MIX_THRESHOLD,
    DRIFT_TIMING_THRESHOLD, DRIFT_MIN_SAMPLES, STAND_SHORT,
)
from engine.simulator.engine import GameEvent


@dataclass
class DriftSignal:
    drift_type: str
    scope: str
    magnitude: float
    direction: str
    time_window: int
    detail: str

    @property
    def severity(self) -> str:
        abs_mag = abs(self.magnitude)
        if abs_mag >= 0.40:
            return "critical"
        elif abs_mag >= 0.25:
            return "warning"
        else:
            return "info"

    def to_dict(self) -> dict:
        return {
            "drift_type": self.drift_type,
            "scope": self.scope,
            "magnitude": round(self.magnitude, 3),
            "direction": self.direction,
            "time_window": self.time_window,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass
class DriftReport:
    time_window: int
    signals: list[DriftSignal] = field(default_factory=list)
    overall_volume_drift: float = 0.0
    stand_drifts: dict[str, float] = field(default_factory=dict)
    item_drifts: dict[str, float] = field(default_factory=dict)
    category_mix_drift: dict[str, float] = field(default_factory=dict)

    @property
    def has_significant_drift(self) -> bool:
        return any(s.severity in ("warning", "critical") for s in self.signals)

    def to_dict(self) -> dict:
        return {
            "time_window": self.time_window,
            "overall_volume_drift": round(self.overall_volume_drift, 3),
            "stand_drifts": {STAND_SHORT.get(k, k): round(v, 3) for k, v in self.stand_drifts.items()},
            "has_significant_drift": self.has_significant_drift,
            "signals": [s.to_dict() for s in self.signals],
        }


class DriftDetector:
    def __init__(self, forecast: dict):
        self.stand_forecast = forecast["stand_forecast"]
        self.item_forecast = forecast["item_forecast"]
        self.stand_item_forecast = forecast.get("stand_item_forecast")

        self._actual_by_stand_window: dict[tuple[str, int], int] = {}
        self._actual_by_item_window: dict[tuple[str, int], int] = {}
        self._actual_by_category_window: dict[tuple[str, int], int] = {}
        self._actual_by_stand_item_window: dict[tuple[str, str, int], int] = {}
        self._actual_by_window: dict[int, int] = {}
        self._event_count_by_window: dict[int, int] = {}

        self._fc_stand = {}
        for _, row in self.stand_forecast.iterrows():
            key = (row["stand"], int(row["time_window"]))
            self._fc_stand[key] = int(row["expected_qty"])

        self._fc_item = {}
        for _, row in self.item_forecast.iterrows():
            key = (row["item"], int(row["time_window"]))
            self._fc_item[key] = int(row["expected_qty"])

        self._fc_stand_item: dict[tuple[str, str, int], int] = {}
        if self.stand_item_forecast is not None:
            for _, row in self.stand_item_forecast.iterrows():
                key = (row["stand"], row["item"], int(row["time_window"]))
                self._fc_stand_item[key] = int(row["expected_qty"])

        self._cumulative_actual = 0
        self._cumulative_forecast = 0
        self._drift_history: list[DriftReport] = []

    def ingest_event(self, event: GameEvent) -> None:
        tw = event.time_window
        stand = event.stand
        item = event.item
        cat = event.category
        qty = event.qty

        self._actual_by_stand_window[(stand, tw)] = self._actual_by_stand_window.get((stand, tw), 0) + qty
        self._actual_by_item_window[(item, tw)] = self._actual_by_item_window.get((item, tw), 0) + qty
        self._actual_by_category_window[(cat, tw)] = self._actual_by_category_window.get((cat, tw), 0) + qty
        self._actual_by_stand_item_window[(stand, item, tw)] = self._actual_by_stand_item_window.get((stand, item, tw), 0) + qty
        self._actual_by_window[tw] = self._actual_by_window.get(tw, 0) + qty
        self._event_count_by_window[tw] = self._event_count_by_window.get(tw, 0) + 1
        self._cumulative_actual += qty

    def check_drift(self, time_window: int) -> DriftReport:
        report = DriftReport(time_window=time_window)
        signals = []

        actual_total = self._actual_by_window.get(time_window, 0)
        fc_total = sum(v for (s, tw), v in self._fc_stand.items() if tw == time_window)

        if fc_total > 0 and self._event_count_by_window.get(time_window, 0) >= DRIFT_MIN_SAMPLES:
            vol_drift = (actual_total - fc_total) / fc_total
            report.overall_volume_drift = vol_drift

            if abs(vol_drift) >= DRIFT_VOLUME_THRESHOLD:
                direction = "above" if vol_drift > 0 else "below"
                signals.append(DriftSignal(
                    drift_type="volume", scope="overall",
                    magnitude=vol_drift, direction=direction,
                    time_window=time_window,
                    detail=f"Total demand {vol_drift:+.0%} vs forecast ({actual_total} vs {fc_total} expected)",
                ))

        stands_this_window = {s for (s, tw) in self._actual_by_stand_window if tw == time_window}
        for stand in stands_this_window:
            actual = self._actual_by_stand_window.get((stand, time_window), 0)
            fc = self._fc_stand.get((stand, time_window), 0)
            if fc > 0:
                drift = (actual - fc) / fc
                short = STAND_SHORT.get(stand, stand)
                report.stand_drifts[stand] = drift
                if abs(drift) >= DRIFT_VOLUME_THRESHOLD:
                    direction = "above" if drift > 0 else "below"
                    signals.append(DriftSignal(
                        drift_type="volume", scope=short,
                        magnitude=drift, direction=direction,
                        time_window=time_window,
                        detail=f"{short}: {actual} actual vs {fc} forecast ({drift:+.0%})",
                    ))

        items_this_window = {i for (i, tw) in self._actual_by_item_window if tw == time_window}
        for item in items_this_window:
            actual = self._actual_by_item_window.get((item, time_window), 0)
            fc = self._fc_item.get((item, time_window), 0)
            if fc > 0:
                drift = (actual - fc) / fc
                report.item_drifts[item] = drift
                if abs(drift) >= 0.30:
                    direction = "above" if drift > 0 else "below"
                    signals.append(DriftSignal(
                        drift_type="mix", scope=item,
                        magnitude=drift, direction=direction,
                        time_window=time_window,
                        detail=f"{item}: {actual} actual vs {fc} forecast ({drift:+.0%})",
                    ))

        self._cumulative_forecast += fc_total
        report.signals = sorted(signals, key=lambda s: -abs(s.magnitude))
        self._drift_history.append(report)
        return report

    @property
    def history(self) -> list[DriftReport]:
        return self._drift_history

    def cumulative_drift(self) -> float:
        if self._cumulative_forecast == 0:
            return 0.0
        return (self._cumulative_actual - self._cumulative_forecast) / self._cumulative_forecast

    def summary(self) -> dict:
        all_signals = [s for r in self._drift_history for s in r.signals]
        return {
            "total_windows": len(self._drift_history),
            "windows_with_drift": sum(1 for r in self._drift_history if r.has_significant_drift),
            "total_signals": len(all_signals),
            "critical_signals": sum(1 for s in all_signals if s.severity == "critical"),
            "warning_signals": sum(1 for s in all_signals if s.severity == "warning"),
            "cumulative_drift": f"{self.cumulative_drift():+.1%}",
            "total_actual": self._cumulative_actual,
            "total_forecast": self._cumulative_forecast,
        }
