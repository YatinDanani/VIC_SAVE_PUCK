"""Predict optimal dates/types for events, promotions, and early-bird sales."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd
import numpy as np
import anthropic

from engine.data.enricher import enrich_games
from engine.data.loader import load_merged


@dataclass
class PromoRecommendation:
    recommendation_type: str
    target_games: list[str]
    description: str
    expected_impact: str
    confidence: float
    rationale: str

    def to_dict(self) -> dict:
        return {
            "type": self.recommendation_type,
            "target_games": self.target_games,
            "description": self.description,
            "expected_impact": self.expected_impact,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


def analyze_promo_opportunities() -> list[PromoRecommendation]:
    games = enrich_games()
    merged = load_merged()
    recommendations = []

    # 1. Low-attendance patterns
    median_att = games["attendance"].median()
    low_att_games = games[games["attendance"] < median_att * 0.8]
    low_att_days = low_att_games["day_of_week"].value_counts()
    low_att_patterns = []
    for day, count in low_att_days.items():
        total_day = len(games[games["day_of_week"] == day])
        if total_day > 0 and count / total_day > 0.5:
            avg_att = low_att_games[low_att_games["day_of_week"] == day]["attendance"].mean()
            low_att_patterns.append(
                f"{day} games: {count}/{total_day} below median, avg attendance {avg_att:.0f}"
            )

    if low_att_patterns:
        recommendations.append(PromoRecommendation(
            recommendation_type="promo",
            target_games=[p.split(":")[0].strip() for p in low_att_patterns],
            description="Schedule promotions on historically low-attendance days",
            expected_impact="Could boost attendance 15-30% on weak days",
            confidence=0.75,
            rationale="\n".join(low_att_patterns),
        ))

    # 2. Promo effectiveness
    promo_games = games[games["is_promo"]]
    non_promo_games = games[~games["is_promo"] & ~games["is_playoff"]]
    if len(promo_games) > 0 and len(non_promo_games) > 0:
        promo_qpc = promo_games["qty_per_cap"].mean()
        non_promo_qpc = non_promo_games["qty_per_cap"].mean()
        lift = (promo_qpc - non_promo_qpc) / non_promo_qpc * 100

        recommendations.append(PromoRecommendation(
            recommendation_type="promo",
            target_games=promo_games["game_date"].dt.strftime("%Y-%m-%d").tolist(),
            description=f"Promo games show {lift:+.0f}% per-capita spend vs regular games",
            expected_impact=f"Avg {promo_qpc:.2f} vs {non_promo_qpc:.2f} qty/cap",
            confidence=0.6 if len(promo_games) < 5 else 0.8,
            rationale=f"Based on {len(promo_games)} promo games vs {len(non_promo_games)} regular games",
        ))

    # 3. Early-bird opportunity
    pre_game_volume = merged[merged["mins_from_puck_drop"] < 0].groupby(
        merged["game_date"]
    )["Qty"].sum().reset_index(name="pre_game_qty")
    total_volume = merged.groupby("game_date")["Qty"].sum().reset_index(name="total_qty")
    pre_ratio = pre_game_volume.merge(total_volume, on="game_date")
    pre_ratio["pre_pct"] = pre_ratio["pre_game_qty"] / pre_ratio["total_qty"]

    low_pre = pre_ratio[pre_ratio["pre_pct"] < pre_ratio["pre_pct"].quantile(0.25)]
    if len(low_pre) > 3:
        recommendations.append(PromoRecommendation(
            recommendation_type="early_bird",
            target_games=["Games with slow pre-game sales"],
            description="Early-bird food specials for games with slow pre-game sales",
            expected_impact="Could shift 10-15% of P1 demand to pre-game, reducing intermission congestion",
            confidence=0.7,
            rationale=f"{len(low_pre)} games have below-average pre-game sales",
        ))

    # 4. Per-cap by temperature
    games_copy = games.copy()
    games_copy["temp_band"] = pd.cut(
        games_copy["temp_mean"], bins=[-10, 3, 8, 13, 20], labels=["Cold", "Cool", "Mild", "Warm"]
    )
    temp_qpc = games_copy.groupby("temp_band", observed=True)["qty_per_cap"].mean()
    if len(temp_qpc) > 1:
        best_temp = temp_qpc.idxmax()
        recommendations.append(PromoRecommendation(
            recommendation_type="scheduling",
            target_games=[str(best_temp)],
            description=f"Highest per-cap spend in '{best_temp}' temperature band",
            expected_impact=f"Per-cap: {temp_qpc.to_dict()}",
            confidence=0.65,
            rationale="Temperature directly affects beer-to-food ratio and total spending",
        ))

    # 5. Intermission congestion
    int1 = merged[(merged["mins_from_puck_drop"] >= 20) & (merged["mins_from_puck_drop"] < 38)]
    int1_stand_load = int1.groupby(["game_date", "stand"])["Qty"].sum().reset_index()
    int1_concentration = int1_stand_load.groupby("game_date")["Qty"].apply(
        lambda x: x.max() / x.sum() if x.sum() > 0 else 0
    )
    high_concentration = int1_concentration[int1_concentration > 0.4]
    if len(high_concentration) > 5:
        recommendations.append(PromoRecommendation(
            recommendation_type="event",
            target_games=["All intermissions"],
            description="Deploy mobile/pop-up stations during intermissions",
            expected_impact="Reduce max-stand concentration from 40%+ to sub-35%",
            confidence=0.8,
            rationale=f"{len(high_concentration)} of {len(int1_concentration)} games show >40% demand concentrated at one stand during INT1",
        ))

    return recommendations


def generate_ai_event_recommendations(
    recommendations: list[PromoRecommendation] | None = None,
) -> str:
    if recommendations is None:
        recommendations = analyze_promo_opportunities()

    recs_text = "\n\n".join(
        f"**{r.recommendation_type.upper()}: {r.description}**\n"
        f"Impact: {r.expected_impact}\n"
        f"Confidence: {r.confidence:.0%}\n"
        f"Rationale: {r.rationale}"
        for r in recommendations
    )

    games = enrich_games()
    game_summary = (
        f"Total games: {len(games)}\n"
        f"Attendance range: {games['attendance'].min()}-{games['attendance'].max()}\n"
        f"Median attendance: {games['attendance'].median():.0f}\n"
        f"Promo games: {games['is_promo'].sum()}\n"
        f"Playoff games: {games['is_playoff'].sum()}\n"
        f"Archetypes: {games['archetype'].value_counts().to_dict()}\n"
        f"Day distribution: {games['day_of_week'].value_counts().to_dict()}"
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=(
                "You are a strategic events consultant for a WHL hockey arena. "
                "Given data-driven insights about attendance, spending patterns, and demand, "
                "produce a concise actionable strategy for promotions, events, and early-bird offers. "
                "Be specific with recommendations. Use bullet points."
            ),
            messages=[{
                "role": "user",
                "content": f"GAME DATA OVERVIEW:\n{game_summary}\n\nDATA-DRIVEN INSIGHTS:\n{recs_text}\n\n"
                           f"Based on these insights, recommend a specific promotional strategy for the remaining season.",
            }],
        )
        return response.content[0].text
    except Exception as e:
        lines = ["EVENT OPTIMIZATION RECOMMENDATIONS", "=" * 40, ""]
        for r in recommendations:
            lines.append(f"[{r.recommendation_type.upper()}] {r.description}")
            lines.append(f"  Impact: {r.expected_impact}")
            lines.append(f"  Confidence: {r.confidence:.0%}")
            lines.append("")
        lines.append(f"(AI synthesis unavailable: {e})")
        return "\n".join(lines)
