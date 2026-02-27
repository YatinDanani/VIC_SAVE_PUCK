"""Convert dataclasses and domain objects to JSON-safe dicts."""

from __future__ import annotations

from vic_save_puck.models.drift import DriftReport, DriftSignal
from vic_save_puck.models.traffic_light import OverallStatus, StandStatus, Status
from vic_save_puck.ai.reasoning import ReasoningResult
from vic_save_puck.config import STAND_SHORT


def serialize_drift_signal(s: DriftSignal) -> dict:
    return {
        "drift_type": s.drift_type,
        "scope": s.scope,
        "magnitude": round(s.magnitude, 3),
        "direction": s.direction,
        "time_window": s.time_window,
        "detail": s.detail,
        "severity": s.severity,
    }


def serialize_drift_report(r: DriftReport) -> dict:
    return {
        "time_window": r.time_window,
        "overall_volume_drift": round(r.overall_volume_drift, 3),
        "has_significant_drift": r.has_significant_drift,
        "stand_drifts": {
            STAND_SHORT.get(k, k): round(v, 3)
            for k, v in r.stand_drifts.items()
        },
        "item_drifts": {
            k: round(v, 3)
            for k, v in sorted(r.item_drifts.items(), key=lambda x: -abs(x[1]))[:10]
        },
        "signals": [serialize_drift_signal(s) for s in r.signals[:10]],
    }


def serialize_stand_status(ss: StandStatus) -> dict:
    return {
        "stand": ss.stand,
        "short_name": ss.short_name,
        "status": ss.status.value,
        "drift_pct": round(ss.drift_pct, 3),
        "forecast_qty": ss.forecast_qty,
        "actual_qty": ss.actual_qty,
        "trend": ss.trend,
    }


def serialize_overall_status(os: OverallStatus) -> dict:
    return {
        "time_window": os.time_window,
        "overall_status": os.overall_status.value,
        "overall_drift": round(os.overall_drift, 3),
        "cumulative_drift": round(os.cumulative_drift, 3),
        "stands": [serialize_stand_status(ss) for ss in os.stand_statuses],
    }


def serialize_reasoning_result(r: ReasoningResult) -> dict:
    return {
        "cause": r.cause,
        "confidence": round(r.confidence, 2),
        "actions": r.actions,
        "alert_text": r.alert_text,
    }


def serialize_forecast_summary(forecast: dict) -> dict:
    """Summarize forecast for initial sim:started message."""
    item_fc = forecast["item_forecast"]
    top_items = (
        item_fc.groupby("item")[["expected_qty", "prep_qty"]]
        .sum()
        .sort_values("expected_qty", ascending=False)
        .head(10)
    )

    total_expected = int(item_fc["expected_qty"].sum())
    total_prep = int(item_fc["prep_qty"].sum())

    return {
        "archetype": forecast["archetype"],
        "attendance": forecast["attendance"],
        "scale_factor": round(forecast["scale_factor"], 2),
        "beer_factor": round(forecast["beer_factor"], 2),
        "total_forecast": total_expected,
        "total_prep": total_prep,
        "prep_pct": round(total_prep / total_expected * 100, 1) if total_expected > 0 else 0,
        "top_items": [
            {
                "item": item,
                "forecast": int(row["expected_qty"]),
                "prep": int(row["prep_qty"]),
            }
            for item, row in top_items.iterrows()
        ],
    }
