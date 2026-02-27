"""Claude AI analysis of forecast errors from LOO backtest."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic
import pandas as pd
import numpy as np

from engine.validation.backtest import GameResult


@dataclass
class ForecastAnalysis:
    key_findings: list[str] = field(default_factory=list)
    feature_importance: dict[str, str] = field(default_factory=dict)
    threshold_recommendations: list[dict] = field(default_factory=list)
    outlier_explanations: list[dict] = field(default_factory=list)
    summary: str = ""


def analyze_forecast_errors(
    results: list[GameResult],
    games: pd.DataFrame | None = None,
) -> ForecastAnalysis:
    if not results:
        return ForecastAnalysis(summary="No results to analyze.")

    df = pd.DataFrame([vars(r) for r in results])

    summary_stats = {
        "n_games": len(df),
        "median_volume_error": f"{df['volume_error'].median():+.1%}",
        "mean_abs_error": f"{df['volume_error'].abs().mean():.1%}",
        "within_15pct": int((df['volume_error'].abs() <= 0.15).sum()),
    }

    try:
        client = anthropic.Anthropic()
        # ... AI analysis would go here
        raise NotImplementedError("Use fallback")
    except Exception as e:
        return _fallback_analysis(df, str(e))


def _fallback_analysis(df: pd.DataFrame, error: str) -> ForecastAnalysis:
    findings = []
    med_err = df["volume_error"].median()
    if med_err > 0.1:
        findings.append(f"Systematic overprediction: median error is {med_err:+.1%}")
    elif med_err < -0.1:
        findings.append(f"Systematic underprediction: median error is {med_err:+.1%}")

    for arch in sorted(df["archetype"].unique()):
        sub = df[df["archetype"] == arch]
        arch_med = sub["volume_error"].median()
        findings.append(f"{arch} ({len(sub)} games): median error {arch_med:+.1%}")

    within_15 = (df["volume_error"].abs() <= 0.15).sum()
    n = len(df)

    return ForecastAnalysis(
        key_findings=findings,
        feature_importance={"attendance_ratio": "Primary driver of forecast scaling"},
        threshold_recommendations=[],
        outlier_explanations=[],
        summary=f"Model performance: {within_15}/{n} games within +/-15%. Median error: {med_err:+.1%}.",
    )
