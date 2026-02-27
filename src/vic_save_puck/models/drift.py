"""Real-time drift detection: compare streaming actuals to forecast."""

from __future__ import annotations

from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from vic_save_puck.config import (
    DRIFT_VOLUME_THRESHOLD, DRIFT_MIX_THRESHOLD,
    DRIFT_TIMING_THRESHOLD, DRIFT_MIN_SAMPLES, STAND_SHORT,
)
from vic_save_puck.simulator.engine import GameEvent


@dataclass
class DriftSignal:
    """A detected drift signal."""
    drift_type: str          # "volume", "mix", "timing"
    scope: str               # "overall", stand name, or item name
    magnitude: float         # signed: +0.25 = 25% above forecast
    direction: str           # "above" or "below"
    time_window: int
    detail: str              # human-readable detail

    @property
    def severity(self) -> str:
        abs_mag = abs(self.magnitude)
        if abs_mag >= 0.40:
            return "critical"
        elif abs_mag >= 0.25:
            return "warning"
        else:
            return "info"

    def __str__(self) -> str:
        pct = f"{self.magnitude:+.0%}"
        return f"[{self.severity.upper():8}] T+{self.time_window:>3}min {self.drift_type:7} | {self.scope:20} | {pct:>6} | {self.detail}"


@dataclass
class DriftReport:
    """Collection of drift signals for a time window."""
    time_window: int
    signals: list[DriftSignal] = field(default_factory=list)
    overall_volume_drift: float = 0.0
    stand_drifts: dict[str, float] = field(default_factory=dict)
    item_drifts: dict[str, float] = field(default_factory=dict)
    category_mix_drift: dict[str, float] = field(default_factory=dict)

    @property
    def has_significant_drift(self) -> bool:
        return any(s.severity in ("warning", "critical") for s in self.signals)

    def __str__(self) -> str:
        if not self.signals:
            return f"T+{self.time_window}min: No significant drift"
        lines = [f"── Drift Report T+{self.time_window}min ──"]
        for s in self.signals:
            lines.append(f"  {s}")
        return "\n".join(lines)


class DriftDetector:
    """
    Maintains rolling comparison of actual vs forecast.
    Call `ingest_event()` for each incoming event, and `check_drift()` per window.
    """

    def __init__(self, forecast: dict):
        self.stand_forecast = forecast["stand_forecast"]
        self.item_forecast = forecast["item_forecast"]
        self.stand_item_forecast = forecast.get("stand_item_forecast")

        # Accumulate actuals per window
        self._actual_by_stand_window: dict[tuple[str, int], int] = {}
        self._actual_by_item_window: dict[tuple[str, int], int] = {}
        self._actual_by_category_window: dict[tuple[str, int], int] = {}
        self._actual_by_stand_item_window: dict[tuple[str, str, int], int] = {}
        self._actual_by_window: dict[int, int] = {}
        self._event_count_by_window: dict[int, int] = {}

        # Build forecast lookup dicts
        self._fc_stand = {}
        for _, row in self.stand_forecast.iterrows():
            key = (row["stand"], int(row["time_window"]))
            self._fc_stand[key] = int(row["expected_qty"])

        self._fc_item = {}
        for _, row in self.item_forecast.iterrows():
            key = (row["item"], int(row["time_window"]))
            self._fc_item[key] = int(row["expected_qty"])

        # Stand × item forecast lookup
        self._fc_stand_item: dict[tuple[str, str, int], int] = {}
        if self.stand_item_forecast is not None:
            for _, row in self.stand_item_forecast.iterrows():
                key = (row["stand"], row["item"], int(row["time_window"]))
                self._fc_stand_item[key] = int(row["expected_qty"])

        # Running totals for cumulative drift
        self._cumulative_actual = 0
        self._cumulative_forecast = 0
        self._drift_history: list[DriftReport] = []

    def ingest_event(self, event: GameEvent) -> None:
        """Record an incoming event."""
        tw = event.time_window
        stand = event.stand
        item = event.item
        cat = event.category
        qty = event.qty

        key_sw = (stand, tw)
        key_iw = (item, tw)
        key_cw = (cat, tw)

        self._actual_by_stand_window[key_sw] = self._actual_by_stand_window.get(key_sw, 0) + qty
        self._actual_by_item_window[key_iw] = self._actual_by_item_window.get(key_iw, 0) + qty
        self._actual_by_category_window[key_cw] = self._actual_by_category_window.get(key_cw, 0) + qty
        key_siw = (stand, item, tw)
        self._actual_by_stand_item_window[key_siw] = self._actual_by_stand_item_window.get(key_siw, 0) + qty
        self._actual_by_window[tw] = self._actual_by_window.get(tw, 0) + qty
        self._event_count_by_window[tw] = self._event_count_by_window.get(tw, 0) + 1
        self._cumulative_actual += qty

    def check_drift(self, time_window: int) -> DriftReport:
        """Analyze drift for a completed time window."""
        report = DriftReport(time_window=time_window)
        signals = []

        # ── Overall volume drift ─────────────────────────────────────────
        actual_total = self._actual_by_window.get(time_window, 0)
        fc_total = sum(
            v for (s, tw), v in self._fc_stand.items() if tw == time_window
        )

        if fc_total > 0 and self._event_count_by_window.get(time_window, 0) >= DRIFT_MIN_SAMPLES:
            vol_drift = (actual_total - fc_total) / fc_total
            report.overall_volume_drift = vol_drift

            if abs(vol_drift) >= DRIFT_VOLUME_THRESHOLD:
                direction = "above" if vol_drift > 0 else "below"
                signals.append(DriftSignal(
                    drift_type="volume",
                    scope="overall",
                    magnitude=vol_drift,
                    direction=direction,
                    time_window=time_window,
                    detail=f"Total demand {vol_drift:+.0%} vs forecast ({actual_total} vs {fc_total} expected)",
                ))

        # ── Per-stand drift ──────────────────────────────────────────────
        stands_this_window = {
            s for (s, tw) in self._actual_by_stand_window if tw == time_window
        }
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
                        drift_type="volume",
                        scope=short,
                        magnitude=drift,
                        direction=direction,
                        time_window=time_window,
                        detail=f"{short}: {actual} actual vs {fc} forecast ({drift:+.0%})",
                    ))
            elif actual > DRIFT_MIN_SAMPLES:
                # Unexpected stand activity
                report.stand_drifts[stand] = float("inf")
                short = STAND_SHORT.get(stand, stand)
                signals.append(DriftSignal(
                    drift_type="volume",
                    scope=short,
                    magnitude=1.0,
                    direction="above",
                    time_window=time_window,
                    detail=f"{short}: {actual} actual with no forecast (untracked stand?)",
                ))

        # ── Per-item drift (top movers only) ─────────────────────────────
        items_this_window = {
            i for (i, tw) in self._actual_by_item_window if tw == time_window
        }
        for item in items_this_window:
            actual = self._actual_by_item_window.get((item, time_window), 0)
            fc = self._fc_item.get((item, time_window), 0)
            if fc > 0:
                drift = (actual - fc) / fc
                report.item_drifts[item] = drift

                if abs(drift) >= 0.30:  # higher threshold for items (more noisy)
                    direction = "above" if drift > 0 else "below"
                    signals.append(DriftSignal(
                        drift_type="mix",
                        scope=item,
                        magnitude=drift,
                        direction=direction,
                        time_window=time_window,
                        detail=f"{item}: {actual} actual vs {fc} forecast ({drift:+.0%})",
                    ))

        # ── Category mix drift ───────────────────────────────────────────
        cats_this_window = {
            c for (c, tw) in self._actual_by_category_window if tw == time_window
        }
        total_actual_cat = sum(
            self._actual_by_category_window.get((c, time_window), 0)
            for c in cats_this_window
        )
        if total_actual_cat > DRIFT_MIN_SAMPLES:
            for cat in cats_this_window:
                actual_cat = self._actual_by_category_window.get((cat, time_window), 0)
                actual_share = actual_cat / total_actual_cat

                # Compute forecast share from item forecasts by category
                # Simplified: just track the shift
                report.category_mix_drift[cat] = actual_share

        # ── Cumulative drift tracking ────────────────────────────────────
        self._cumulative_forecast += fc_total

        report.signals = sorted(signals, key=lambda s: -abs(s.magnitude))
        self._drift_history.append(report)
        return report

    @property
    def history(self) -> list[DriftReport]:
        return self._drift_history

    def cumulative_drift(self) -> float:
        """Overall cumulative drift so far."""
        if self._cumulative_forecast == 0:
            return 0.0
        return (self._cumulative_actual - self._cumulative_forecast) / self._cumulative_forecast

    def stand_load_analysis(self, time_window: int) -> list[dict]:
        """
        Analyze per-stand load and suggest redistribution.

        Returns list of {stand, item, actual, forecast, drift, overloaded, suggestion}
        """
        results = []
        stands_this_window = {
            s for (s, tw) in self._actual_by_stand_window if tw == time_window
        }

        for stand in stands_this_window:
            actual_total = self._actual_by_stand_window.get((stand, time_window), 0)
            fc_total = self._fc_stand.get((stand, time_window), 0)
            stand_drift = (actual_total - fc_total) / fc_total if fc_total > 0 else 0

            # Find top items at this stand
            items_at_stand = {
                i for (s, i, tw) in self._actual_by_stand_item_window
                if s == stand and tw == time_window
            }
            for item in items_at_stand:
                actual = self._actual_by_stand_item_window.get((stand, item, time_window), 0)
                fc = self._fc_stand_item.get((stand, item, time_window), 0)
                item_drift = (actual - fc) / fc if fc > 0 else 0

                # Find alternative stands that sell this item and are underloaded
                suggestion = None
                if item_drift > 0.30 and actual >= 5:
                    alt_stands = []
                    for (s2, i2, tw2), fc2 in self._fc_stand_item.items():
                        if i2 == item and tw2 == time_window and s2 != stand and fc2 > 0:
                            actual2 = self._actual_by_stand_item_window.get((s2, item, time_window), 0)
                            drift2 = (actual2 - fc2) / fc2 if fc2 > 0 else 0
                            if drift2 < 0.15:  # underloaded
                                alt_stands.append({
                                    "stand": s2,
                                    "capacity": fc2 - actual2,
                                    "drift": drift2,
                                })
                    if alt_stands:
                        best = max(alt_stands, key=lambda x: x["capacity"])
                        short_alt = STAND_SHORT.get(best["stand"], best["stand"])
                        short_src = STAND_SHORT.get(stand, stand)
                        suggestion = f"Redirect {item} demand from {short_src} to {short_alt} (has {best['capacity']} units capacity)"

                results.append({
                    "stand": stand,
                    "item": item,
                    "actual": actual,
                    "forecast": fc,
                    "drift": item_drift,
                    "overloaded": item_drift > 0.30 and actual >= 5,
                    "suggestion": suggestion,
                })

        # Sort: overloaded first, then by drift magnitude
        results.sort(key=lambda r: (-r["overloaded"], -abs(r["drift"])))
        return results

    def summary(self) -> dict:
        """Summary stats across all windows."""
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
