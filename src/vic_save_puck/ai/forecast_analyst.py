"""Claude AI analysis of forecast errors from LOO backtest."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic
import pandas as pd
import numpy as np

from vic_save_puck.validation.backtest import GameResult


@dataclass
class ForecastAnalysis:
    """Structured output from Claude's forecast error analysis."""
    key_findings: list[str] = field(default_factory=list)
    feature_importance: dict[str, str] = field(default_factory=dict)
    threshold_recommendations: list[dict] = field(default_factory=list)
    outlier_explanations: list[dict] = field(default_factory=list)
    summary: str = ""


SYSTEM_PROMPT = """You are a sports venue F&B demand forecasting analyst. You analyze leave-one-out cross-validation results from a forecasting model used at Save on Foods Memorial Centre (WHL Victoria Royals hockey).

The forecast computes expected_qty = avg_qty_per_game * (attendance / reference_attendance) with adjustments for temperature, promos, and playoffs.

Your job: analyze the error patterns, identify systematic biases, and recommend improvements.

RESPONSE FORMAT (JSON):
{
  "key_findings": ["finding1", "finding2", ...],
  "feature_importance": {"feature_name": "description of impact", ...},
  "threshold_recommendations": [
    {"parameter": "name", "current": "value", "recommended": "value", "rationale": "why"}
  ],
  "outlier_explanations": [
    {"game": "date vs opponent", "error": "+X%", "likely_cause": "explanation"}
  ],
  "summary": "2-3 sentence executive summary"
}"""


def analyze_forecast_errors(
    results: list[GameResult],
    games: pd.DataFrame | None = None,
) -> ForecastAnalysis:
    """Use Claude to analyze forecast error patterns.

    Args:
        results: List of GameResult from LOO backtest.
        games: Enriched games DataFrame for additional context.

    Returns:
        ForecastAnalysis with AI-generated insights, or rule-based fallback.
    """
    if not results:
        return ForecastAnalysis(summary="No results to analyze.")

    df = pd.DataFrame([vars(r) for r in results])

    # Build summary stats
    summary_stats = {
        "n_games": len(df),
        "median_volume_error": f"{df['volume_error'].median():+.1%}",
        "mean_abs_error": f"{df['volume_error'].abs().mean():.1%}",
        "mean_stand_mape": f"{df['stand_mape'].mean():.1%}",
        "mean_item_mape": f"{df['item_mape'].mean():.1%}",
        "within_15pct": int((df['volume_error'].abs() <= 0.15).sum()),
        "within_25pct": int((df['volume_error'].abs() <= 0.25).sum()),
        "overpredictions": int((df['volume_error'] > 0).sum()),
        "underpredictions": int((df['volume_error'] < 0).sum()),
    }

    # Per-archetype stats
    arch_stats = {}
    for arch in df["archetype"].unique():
        sub = df[df["archetype"] == arch]
        arch_stats[arch] = {
            "count": len(sub),
            "median_error": f"{sub['volume_error'].median():+.1%}",
            "mean_abs_error": f"{sub['volume_error'].abs().mean():.1%}",
        }

    # Per-game table (sorted by abs error descending)
    df_sorted = df.sort_values("volume_error", key=abs, ascending=False)
    game_rows = []
    for _, row in df_sorted.iterrows():
        game_rows.append({
            "date": str(row["game_date"].date()),
            "opponent": row["opponent"],
            "archetype": row["archetype"],
            "attendance": int(row["attendance"]),
            "actual": int(row["actual_total"]),
            "forecast": int(row["forecast_total"]),
            "error": f"{row['volume_error']:+.1%}",
        })

    # Add game-level features if available
    if games is not None:
        for gr in game_rows:
            gd = pd.Timestamp(gr["date"])
            match = games[games["game_date"] == gd]
            if not match.empty:
                g = match.iloc[0]
                gr["temp_mean"] = round(float(g.get("temp_mean", 0)), 1)
                gr["is_promo"] = bool(g.get("is_promo", False))
                gr["is_weekend"] = bool(g.get("is_weekend", False))
                gr["is_playoff"] = bool(g.get("is_playoff", False))
                gr["division"] = str(g.get("opponent_division", ""))

    user_message = f"""BACKTEST SUMMARY:
{json.dumps(summary_stats, indent=2)}

PER-ARCHETYPE STATS:
{json.dumps(arch_stats, indent=2)}

PER-GAME RESULTS (sorted by |error|, top errors first):
{json.dumps(game_rows[:30], indent=2)}

Analyze the error patterns. Identify systematic biases, feature-driven patterns, and recommend model improvements. Respond with JSON only."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = response.content[0].text
        parsed = _parse_json_response(raw)

        return ForecastAnalysis(
            key_findings=parsed.get("key_findings", []),
            feature_importance=parsed.get("feature_importance", {}),
            threshold_recommendations=parsed.get("threshold_recommendations", []),
            outlier_explanations=parsed.get("outlier_explanations", []),
            summary=parsed.get("summary", ""),
        )

    except Exception as e:
        return _fallback_analysis(df, str(e))


def _parse_json_response(text: str) -> dict:
    """Extract JSON from model response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {}


def _fallback_analysis(df: pd.DataFrame, error: str) -> ForecastAnalysis:
    """Rule-based fallback when Claude API is unavailable."""
    findings = []

    med_err = df["volume_error"].median()
    if med_err > 0.1:
        findings.append(f"Systematic overprediction: median error is {med_err:+.1%}")
    elif med_err < -0.1:
        findings.append(f"Systematic underprediction: median error is {med_err:+.1%}")

    # Per-archetype
    for arch in sorted(df["archetype"].unique()):
        sub = df[df["archetype"] == arch]
        arch_med = sub["volume_error"].median()
        findings.append(f"{arch} ({len(sub)} games): median error {arch_med:+.1%}")

    # Worst games
    worst = df.nlargest(3, "volume_error")
    outliers = []
    for _, row in worst.iterrows():
        outliers.append({
            "game": f"{row['game_date'].date()} vs {row['opponent']}",
            "error": f"{row['volume_error']:+.1%}",
            "likely_cause": "High overprediction — possible low-energy game or data anomaly",
        })

    within_15 = (df["volume_error"].abs() <= 0.15).sum()
    n = len(df)

    return ForecastAnalysis(
        key_findings=findings,
        feature_importance={"attendance_ratio": "Primary driver of forecast scaling"},
        threshold_recommendations=[],
        outlier_explanations=outliers,
        summary=(
            f"Fallback analysis (AI unavailable: {error}). "
            f"Model overpredicts with median error {med_err:+.1%}. "
            f"{within_15}/{n} games within +/-15%."
        ),
    )
