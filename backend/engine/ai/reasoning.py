"""LLM-powered drift classification, prep adjustments, and shift-manager alerts."""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from engine.models.drift import DriftReport, DriftSignal
from engine.config import STAND_SHORT


@dataclass
class ReasoningResult:
    cause: str
    confidence: float
    actions: list[dict]
    alert_text: str
    raw_reasoning: str

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "confidence": self.confidence,
            "actions": self.actions,
            "alert_text": self.alert_text,
        }


SYSTEM_PROMPT = """You are an AI operations analyst for Save on Foods Memorial Centre, a WHL hockey arena in Victoria, BC. You analyze real-time F&B demand data during hockey games.

Your job: Given drift signals (differences between forecasted and actual demand), classify WHY the drift is happening and recommend specific prep adjustments.

CONTEXT:
- The arena has 5-6 concession stands: Island Canteen (main), TacoTacoTaco, ReMax Fan Deck, Portable Stations, Island Slice, Phillips Bar
- Games have pre-game, 3 periods (20 min each), 2 intermissions (~18 min each)
- Demand peaks during intermissions and pre-game
- Three crowd archetypes: beer_crowd (high alcohol %), mixed, family (low alcohol %)

PREP PHILOSOPHY (asymmetric loss):
- We DELIBERATELY underpredict. Prep targets are 75-95% of forecast depending on perishability.
- Only recommend scaling UP when actual demand is clearly exceeding prep levels.

DRIFT CAUSES:
1. "volume_surge" — overall demand higher than expected
2. "volume_drop" — overall demand lower than expected
3. "untagged_promo" — a promotion wasn't flagged, causing specific item spikes
4. "stand_redistribution" — one stand is down/slow, others absorbing demand
5. "weather_effect" — temperature affecting beer/hot drink mix
6. "timing_shift" — demand curve shifted earlier or later
7. "noise" — random variance, no action needed

RESPONSE FORMAT (JSON):
{
  "cause": "one of the causes above",
  "confidence": 0.0-1.0,
  "actions": [
    {"stand": "stand name", "item": "item name", "action": "increase_prep|decrease_prep|redistribute|hold", "quantity_change_pct": 25}
  ],
  "alert_text": "Plain English alert for the shift manager (2-3 sentences max)"
}"""


def analyze_drift(
    drift_report: DriftReport,
    game_context: dict,
    cumulative_drift: float = 0.0,
    recent_reports: list[DriftReport] | None = None,
) -> ReasoningResult:
    signals_text = "\n".join(str(s) for s in drift_report.signals[:15])
    stand_drifts = {
        STAND_SHORT.get(k, k): f"{v:+.0%}"
        for k, v in drift_report.stand_drifts.items()
        if abs(v) >= 0.15
    }

    recent_context = ""
    if recent_reports:
        for r in recent_reports[-3:]:
            if r.has_significant_drift:
                recent_context += f"\nT+{r.time_window}min: overall {r.overall_volume_drift:+.0%}, "
                top_stands = sorted(r.stand_drifts.items(), key=lambda x: -abs(x[1]))[:3]
                recent_context += ", ".join(
                    f"{STAND_SHORT.get(s, s)} {d:+.0%}" for s, d in top_stands
                )

    user_message = f"""CURRENT WINDOW: T+{drift_report.time_window} minutes from puck drop
GAME: vs {game_context.get('opponent', 'Unknown')} | Attendance: {game_context.get('attendance', '?')} | Archetype: {game_context.get('archetype', '?')}
CUMULATIVE DRIFT: {cumulative_drift:+.1%}

DRIFT SIGNALS THIS WINDOW:
{signals_text}

STAND-LEVEL DRIFTS (significant only):
{json.dumps(stand_drifts, indent=2)}

RECENT TREND:
{recent_context if recent_context else "No significant prior drift"}

Classify the drift cause and recommend actions. Respond with JSON only."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text
        parsed = _parse_json_response(raw)
        return ReasoningResult(
            cause=parsed.get("cause", "noise"),
            confidence=float(parsed.get("confidence", 0.5)),
            actions=parsed.get("actions", []),
            alert_text=parsed.get("alert_text", "No specific alert."),
            raw_reasoning=raw,
        )
    except Exception as e:
        return _fallback_classify(drift_report, cumulative_drift, str(e))


def _parse_json_response(text: str) -> dict:
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


def _fallback_classify(report: DriftReport, cumulative_drift: float, error: str) -> ReasoningResult:
    vol = report.overall_volume_drift
    positive_stands = sum(1 for d in report.stand_drifts.values() if d > 0.2)
    negative_stands = sum(1 for d in report.stand_drifts.values() if d < -0.3)

    if negative_stands >= 1 and positive_stands >= 1:
        cause = "stand_redistribution"
        alert = "Some stands are absorbing demand from underperforming stands. Consider redistributing staff."
    elif vol > 0.3:
        cause = "volume_surge"
        alert = f"Demand is running {vol:+.0%} above forecast. Scale up prep across all stands."
    elif vol < -0.3:
        cause = "volume_drop"
        alert = f"Demand is running {vol:+.0%} below forecast. Consider reducing prep to avoid waste."
    else:
        cause = "noise"
        alert = "Drift within normal variance. No action needed."

    return ReasoningResult(
        cause=cause, confidence=0.5, actions=[],
        alert_text=f"{alert} (AI unavailable: {error})",
        raw_reasoning=f"Fallback classification. Error: {error}",
    )
