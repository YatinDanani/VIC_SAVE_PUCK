"""Build historical game profile templates for demand forecasting."""

from __future__ import annotations

import pandas as pd
import numpy as np

from vic_save_puck.config import TIME_WINDOWS, PROFILES_CACHE
from vic_save_puck.data.loader import load_merged
from vic_save_puck.data.enricher import enrich_games


def build_profiles(force_reload: bool = False) -> dict:
    """
    Build historical game profile templates indexed by archetype.

    Returns dict with keys:
    - 'stand_curves': DataFrame of avg qty per time_window per stand per archetype
    - 'item_curves': DataFrame of avg qty per time_window per item per archetype
    - 'category_mix': DataFrame of category mix % per game phase per archetype
    - 'games': enriched games DataFrame
    """
    if PROFILES_CACHE.exists() and not force_reload:
        return _load_cached_profiles()

    merged = load_merged(force_reload=force_reload)
    games = enrich_games(force_reload=force_reload)

    profiles = build_profiles_from_data(merged, games)

    _save_profiles(profiles)
    return profiles


def build_profiles_from_data(merged: pd.DataFrame, games: pd.DataFrame) -> dict:
    """
    Build profile curves from pre-filtered merged transactions and games DataFrames.

    This is the core profile-building logic, separated so it can be called
    with filtered data (e.g., leave-one-out cross-validation).
    """
    merged = merged.copy()

    # Join archetype into transactions
    arch_map = games.set_index("game_date")["archetype"].to_dict()
    merged["archetype"] = merged["game_date"].map(arch_map).fillna("mixed")

    att_map = games.set_index("game_date")["attendance"].to_dict()
    merged["attendance"] = merged["game_date"].map(att_map)

    # Total games per archetype — used as denominator so sparse items
    # get a low avg (reflecting zero-sale games) instead of being inflated.
    games_per_arch = games.groupby("archetype")["game_date"].nunique().to_dict()

    # ── Stand demand curves (per 10-min window) ──────────────────────────
    stand_curves = (
        merged.groupby(["archetype", "stand", "time_window"])
        .agg(
            total_qty=("Qty", "sum"),
            game_count=("game_date", "nunique"),
        )
        .reset_index()
    )
    stand_curves["arch_game_count"] = stand_curves["archetype"].map(games_per_arch)
    stand_curves["avg_qty"] = (
        stand_curves["total_qty"] / stand_curves["arch_game_count"]
    ).round(2)

    # ── Item demand curves ───────────────────────────────────────────────
    item_curves = (
        merged.groupby(["archetype", "Item", "time_window"])
        .agg(
            total_qty=("Qty", "sum"),
            game_count=("game_date", "nunique"),
        )
        .reset_index()
    )
    item_curves["arch_game_count"] = item_curves["archetype"].map(games_per_arch)
    item_curves["avg_qty"] = (
        item_curves["total_qty"] / item_curves["arch_game_count"]
    ).round(2)

    # ── Stand × Item demand curves (the granular forecast) ────────────────
    stand_item_curves = (
        merged.groupby(["archetype", "stand", "Item", "time_window"])
        .agg(
            total_qty=("Qty", "sum"),
            game_count=("game_date", "nunique"),
        )
        .reset_index()
    )
    stand_item_curves["arch_game_count"] = stand_item_curves["archetype"].map(games_per_arch)
    stand_item_curves["avg_qty"] = (
        stand_item_curves["total_qty"] / stand_item_curves["arch_game_count"]
    ).round(2)

    # ── Category mix by game phase ───────────────────────────────────────
    def assign_phase(mins: float) -> str:
        if pd.isna(mins):
            return "unknown"
        if mins < 0:
            return "pre_game"
        elif mins < 20:
            return "P1"
        elif mins < 38:
            return "INT1"
        elif mins < 58:
            return "P2"
        elif mins < 76:
            return "INT2"
        elif mins < 96:
            return "P3"
        else:
            return "post_game"

    merged["phase"] = merged["mins_from_puck_drop"].apply(assign_phase)

    category_mix = (
        merged.groupby(["archetype", "phase", "category_norm"])
        .agg(total_qty=("Qty", "sum"))
        .reset_index()
    )
    phase_totals = category_mix.groupby(["archetype", "phase"])["total_qty"].transform("sum")
    category_mix["mix_pct"] = (category_mix["total_qty"] / phase_totals * 100).round(1)

    # ── Per-cap normalised stand curves (for attendance scaling) ──────────
    percap_curves = (
        merged.groupby(["archetype", "stand", "time_window"])
        .apply(lambda g: (g["Qty"].sum() / g["attendance"].iloc[0])
               if g["attendance"].iloc[0] and g["attendance"].iloc[0] > 0
               else 0,
               include_groups=False)
        .reset_index(name="qty_per_cap")
    )
    percap_avg = (
        percap_curves.groupby(["archetype", "stand", "time_window"])["qty_per_cap"]
        .mean()
        .reset_index()
    )

    return {
        "stand_curves": stand_curves,
        "item_curves": item_curves,
        "stand_item_curves": stand_item_curves,
        "category_mix": category_mix,
        "percap_curves": percap_avg,
        "games": games,
    }


def _save_profiles(profiles: dict) -> None:
    """Cache profiles to parquet files."""
    for key, df in profiles.items():
        path = PROFILES_CACHE.parent / f"profile_{key}.parquet"
        df.to_parquet(path, index=False)


def _load_cached_profiles() -> dict:
    """Load cached profile parquets."""
    profiles = {}
    for key in ["stand_curves", "item_curves", "stand_item_curves", "category_mix", "percap_curves", "games"]:
        path = PROFILES_CACHE.parent / f"profile_{key}.parquet"
        if path.exists():
            profiles[key] = pd.read_parquet(path)
    return profiles


def query_profile(
    archetype: str = "mixed",
    day_of_week: str | None = None,
    puck_drop_hour: int = 19,
    profiles: dict | None = None,
) -> dict:
    """
    Query for a matching game profile.

    Returns dict with 'stand_curve' and 'item_curve' DataFrames
    filtered to the given archetype.
    """
    if profiles is None:
        profiles = build_profiles()

    stand_curve = profiles["stand_curves"]
    item_curve = profiles["item_curves"]

    # Filter by archetype
    sc = stand_curve[stand_curve["archetype"] == archetype].copy()
    ic = item_curve[item_curve["archetype"] == archetype].copy()

    return {
        "stand_curve": sc,
        "item_curve": ic,
        "archetype": archetype,
    }
