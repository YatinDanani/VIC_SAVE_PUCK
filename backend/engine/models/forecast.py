"""Pre-game demand forecast: given game context, produce a per-stand/item/window plan."""

from __future__ import annotations

import pandas as pd
import numpy as np

from engine.config import (
    STANDS, ARCHETYPE_THRESHOLDS, TIME_WINDOWS,
    ITEM_PERISHABILITY, PREP_TARGET,
)
from engine.data.profiles import build_profiles, query_profile
from engine.data.enricher import enrich_games


def derive_archetype(
    attendance: int,
    puck_drop_hour: int,
    is_playoff: bool,
    is_promo: bool,
    temp_mean: float,
    day_of_week: str = "Fri",
) -> str:
    """Derive expected crowd archetype from game inputs."""
    if is_playoff:
        return "beer_crowd"
    if attendance >= 3500 and puck_drop_hour >= 19 and day_of_week in ("Fri", "Sat"):
        return "beer_crowd"
    if puck_drop_hour < 17:
        return "family"
    if temp_mean < 3 and day_of_week in ("Sun", "Sat"):
        return "family"
    return "mixed"


def generate_forecast(
    attendance: int,
    puck_drop_hour: int = 19,
    is_playoff: bool = False,
    is_promo: bool = False,
    promo_type: str = "",
    temp_mean: float = 8.0,
    day_of_week: str = "Fri",
    profiles: dict | None = None,
) -> dict:
    """Generate a pre-game demand forecast."""
    if profiles is None:
        profiles = build_profiles()

    archetype = derive_archetype(
        attendance, puck_drop_hour, is_playoff, is_promo, temp_mean, day_of_week,
    )

    games_df = profiles["games"]
    stand_curves = profiles["stand_curves"]
    item_curves = profiles["item_curves"]
    stand_item_curves = profiles.get("stand_item_curves")

    arch_games = games_df[games_df["archetype"] == archetype]
    if arch_games.empty:
        arch_games = games_df
    ref_attendance = arch_games["attendance"].mean()

    scale = attendance / ref_attendance if ref_attendance > 0 else 1.0

    sc = stand_curves[stand_curves["archetype"] == archetype].copy()
    if sc.empty:
        sc = stand_curves[stand_curves["archetype"] == "mixed"].copy()
    sc["expected_qty"] = (sc["avg_qty"] * scale).round(1)

    ic = item_curves[item_curves["archetype"] == archetype].copy()
    if ic.empty:
        ic = item_curves[item_curves["archetype"] == "mixed"].copy()
    ic["expected_qty"] = (ic["avg_qty"] * scale).round(1)

    # Temperature adjustment for beer
    temp_delta = temp_mean - 8.0
    beer_factor = 1.0 + (temp_delta * 0.03)
    beer_factor = max(0.7, min(1.5, beer_factor))

    beer_items = ic["Item"].isin(["Draught Beer", "Cans of Beer"])
    ic.loc[beer_items, "expected_qty"] *= beer_factor

    hot_items = ic["Item"].isin(["Hot Drinks", "Coffee & Baileys"])
    ic.loc[hot_items, "expected_qty"] *= (1.0 / beer_factor)

    # Promo overrides
    if is_promo and promo_type:
        promo_lower = promo_type.lower()
        if "dog" in promo_lower:
            dog_items = ic["Item"].isin(["Hot Dog", "Dogs"])
            ic.loc[dog_items, "expected_qty"] *= 2.5

    # Playoff boost
    if is_playoff:
        ic["expected_qty"] *= 1.15

    ic["expected_qty"] = ic["expected_qty"].round(0).astype(int)
    sc["expected_qty"] = sc["expected_qty"].round(0).astype(int)

    def _apply_prep_target(df: pd.DataFrame, item_col: str = "Item") -> pd.DataFrame:
        df["perishability"] = df[item_col].map(ITEM_PERISHABILITY).fillna("medium_hold")
        df["prep_target"] = df["perishability"].map(PREP_TARGET)
        df["prep_qty"] = (df["expected_qty"] * df["prep_target"]).round(0).astype(int)
        return df

    ic = _apply_prep_target(ic, "Item")

    sc = sc[(sc["time_window"] >= -90) & (sc["time_window"] <= 120)]
    ic = ic[(ic["time_window"] >= -90) & (ic["time_window"] <= 120)]

    # Stand × item × time_window forecast
    si_forecast = None
    if stand_item_curves is not None:
        si = stand_item_curves[stand_item_curves["archetype"] == archetype].copy()
        if si.empty:
            si = stand_item_curves[stand_item_curves["archetype"] == "mixed"].copy()
        si["expected_qty"] = (si["avg_qty"] * scale).round(1)

        beer_si = si["Item"].isin(["Draught Beer", "Cans of Beer"])
        si.loc[beer_si, "expected_qty"] *= beer_factor
        hot_si = si["Item"].isin(["Hot Drinks", "Coffee & Baileys"])
        si.loc[hot_si, "expected_qty"] *= (1.0 / beer_factor)
        if is_promo and promo_type and "dog" in promo_type.lower():
            dog_si = si["Item"].isin(["Hot Dog", "Dogs"])
            si.loc[dog_si, "expected_qty"] *= 2.5
        if is_playoff:
            si["expected_qty"] *= 1.15

        si["expected_qty"] = si["expected_qty"].round(0).astype(int)
        si = _apply_prep_target(si, "Item")
        si = si[(si["time_window"] >= -90) & (si["time_window"] <= 120)]
        si_forecast = si[["stand", "Item", "time_window", "expected_qty", "prep_qty", "perishability"]].rename(
            columns={"Item": "item"}
        ).reset_index(drop=True)

    return {
        "stand_forecast": sc[["stand", "time_window", "expected_qty"]].reset_index(drop=True),
        "item_forecast": ic[["Item", "time_window", "expected_qty", "prep_qty", "perishability"]].rename(
            columns={"Item": "item"}
        ).reset_index(drop=True),
        "stand_item_forecast": si_forecast,
        "archetype": archetype,
        "attendance": attendance,
        "scale_factor": round(scale, 3),
        "beer_factor": round(beer_factor, 3),
    }


def forecast_for_game(game_date: str, profiles: dict | None = None) -> dict:
    """Generate forecast for a specific historical game (for backtesting)."""
    if profiles is None:
        profiles = build_profiles()

    games = profiles["games"]
    game = games[games["game_date"] == pd.Timestamp(game_date)]
    if game.empty:
        raise ValueError(f"No game found for date {game_date}")

    g = game.iloc[0]
    return generate_forecast(
        attendance=int(g["attendance"]),
        puck_drop_hour=int(g["puck_drop_hour"]),
        is_playoff=bool(g["is_playoff"]),
        is_promo=bool(g["is_promo"]),
        promo_type=str(g.get("promo_type", "")),
        temp_mean=float(g.get("temp_mean", 8.0)),
        day_of_week=str(g["day_of_week"]),
        profiles=profiles,
    )
