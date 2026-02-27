"""Post-game AI analysis: forecast accuracy, drift handling, waste estimation."""

from __future__ import annotations

import json
import anthropic

from vic_save_puck.models.drift import DriftDetector
from vic_save_puck.ai.reasoning import ReasoningResult


POSTGAME_SYSTEM = """You are an AI post-game analyst for Save on Foods Memorial Centre (WHL hockey arena, Victoria BC). After a game simulation, you produce a concise operations report.

Your report should cover:
1. FORECAST ACCURACY — How well did the pre-game forecast match reality? Break down by stand and by item category.
2. KEY DRIFT EVENTS — What significant deviations occurred and how were they handled?
3. WASTE & REVENUE IMPACT — Estimate waste avoided (overprep items caught early) and revenue captured (underprep items scaled up).
4. RECOMMENDATIONS — What should be done differently for the next similar game?

Keep it actionable and concise. Use bullet points. Write for a non-technical shift manager audience."""


def generate_post_game_report(
    game_context: dict,
    drift_detector: DriftDetector,
    reasoning_results: list[ReasoningResult],
    forecast: dict,
) -> str:
    """Generate a post-game analysis report using Claude."""
    summary = drift_detector.summary()

    # Build drift event timeline
    drift_timeline = []
    for r in drift_detector.history:
        if r.has_significant_drift:
            drift_timeline.append({
                "window": f"T+{r.time_window}min",
                "overall_drift": f"{r.overall_volume_drift:+.0%}",
                "top_stands": {
                    k: f"{v:+.0%}" for k, v in sorted(
                        r.stand_drifts.items(), key=lambda x: -abs(x[1])
                    )[:3]
                },
            })

    # Build reasoning summary
    ai_actions = []
    for rr in reasoning_results:
        ai_actions.append({
            "cause": rr.cause,
            "confidence": rr.confidence,
            "alert": rr.alert_text,
        })

    user_message = f"""GAME SUMMARY:
- Opponent: {game_context.get('opponent', 'Unknown')}
- Date: {game_context.get('date', '?')}
- Attendance: {game_context.get('attendance', '?')}
- Archetype: {game_context.get('archetype', '?')}

FORECAST PERFORMANCE:
- Total forecast: {summary['total_forecast']} units
- Total actual: {summary['total_actual']} units
- Cumulative drift: {summary['cumulative_drift']}
- Windows with significant drift: {summary['windows_with_drift']}/{summary['total_windows']}
- Critical signals: {summary['critical_signals']}
- Warning signals: {summary['warning_signals']}

DRIFT TIMELINE (significant events):
{json.dumps(drift_timeline[:10], indent=2)}

AI INTERVENTIONS:
{json.dumps(ai_actions[:8], indent=2)}

FORECAST CONFIG:
- Archetype used: {forecast.get('archetype', '?')}
- Scale factor: {forecast.get('scale_factor', '?')}
- Beer adjustment: {forecast.get('beer_factor', '?')}

Generate a post-game operations report."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=POSTGAME_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    except Exception as e:
        return _fallback_report(game_context, summary, drift_timeline, str(e))


def _fallback_report(
    game_context: dict,
    summary: dict,
    drift_timeline: list,
    error: str,
) -> str:
    """Generate a basic report without AI."""
    lines = [
        "=" * 60,
        "POST-GAME OPERATIONS REPORT (auto-generated)",
        "=" * 60,
        f"Game: vs {game_context.get('opponent', '?')} | {game_context.get('date', '?')}",
        f"Attendance: {game_context.get('attendance', '?')}",
        "",
        "FORECAST ACCURACY:",
        f"  Total forecast: {summary['total_forecast']} units",
        f"  Total actual: {summary['total_actual']} units",
        f"  Overall drift: {summary['cumulative_drift']}",
        f"  Significant drift windows: {summary['windows_with_drift']}/{summary['total_windows']}",
        "",
        "KEY EVENTS:",
    ]

    for event in drift_timeline[:5]:
        lines.append(f"  {event['window']}: {event['overall_drift']} overall")

    lines.extend([
        "",
        f"(AI analysis unavailable: {error})",
        "=" * 60,
    ])

    return "\n".join(lines)
