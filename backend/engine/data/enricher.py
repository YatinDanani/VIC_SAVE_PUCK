"""Enrich game data with weather, calendar flags, crowd archetypes."""

from __future__ import annotations

import json
import pandas as pd
import numpy as np
from pathlib import Path

from engine.config import (
    VENUE_LAT, VENUE_LON, CACHE_DIR, ENRICHED_CACHE,
    OPPONENT_DISTANCE, OPPONENT_DIVISION,
    ARCHETYPE_THRESHOLDS,
)
from engine.data.loader import load_games, load_merged


WEATHER_CACHE = CACHE_DIR / "weather.json"


def fetch_weather_for_dates(dates: list[str]) -> dict:
    """Fetch historical weather from Open-Meteo for given dates. Caches locally."""
    if WEATHER_CACHE.exists():
        cached = json.loads(WEATHER_CACHE.read_text())
        missing = [d for d in dates if d not in cached]
        if not missing:
            return cached
    else:
        cached = {}
        missing = dates

    if not missing:
        return cached

    import httpx

    min_date = min(missing)
    max_date = max(missing)

    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={VENUE_LAT}&longitude={VENUE_LON}"
        f"&start_date={min_date}&end_date={max_date}"
        f"&daily=temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
        f"precipitation_sum,windspeed_10m_max"
        f"&timezone=America/Vancouver"
    )

    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        dates_list = daily.get("time", [])

        for i, d in enumerate(dates_list):
            cached[d] = {
                "temp_max": daily["temperature_2m_max"][i],
                "temp_min": daily["temperature_2m_min"][i],
                "temp_mean": daily["temperature_2m_mean"][i],
                "precip_mm": daily["precipitation_sum"][i],
                "wind_max_kmh": daily["windspeed_10m_max"][i],
            }
    except Exception as e:
        print(f"Weather fetch failed: {e}. Using defaults.")
        for d in missing:
            cached[d] = {
                "temp_max": 10.0, "temp_min": 5.0, "temp_mean": 7.5,
                "precip_mm": 0.0, "wind_max_kmh": 10.0,
            }

    WEATHER_CACHE.write_text(json.dumps(cached, indent=2))
    return cached


def classify_archetype(game_txns: pd.DataFrame) -> str:
    """Classify a game's crowd archetype based on category mix."""
    total_qty = game_txns["Qty"].sum()
    if total_qty == 0:
        return "mixed"

    beer_qty = game_txns.loc[game_txns["category_norm"] == "Beer", "Qty"].sum()
    beer_share = beer_qty / total_qty

    if beer_share >= ARCHETYPE_THRESHOLDS["beer_crowd"]:
        return "beer_crowd"
    elif beer_share < ARCHETYPE_THRESHOLDS["family"]:
        return "family"
    else:
        return "mixed"


def enrich_games(force_reload: bool = False) -> pd.DataFrame:
    """Enrich games with weather, opponent metadata, calendar flags, archetypes."""
    if ENRICHED_CACHE.exists() and not force_reload:
        return pd.read_parquet(ENRICHED_CACHE)

    games = load_games(force_reload=force_reload)
    merged = load_merged(force_reload=force_reload)

    game_dates = games["game_date"].dt.strftime("%Y-%m-%d").unique().tolist()
    weather = fetch_weather_for_dates(game_dates)

    games["date_str"] = games["game_date"].dt.strftime("%Y-%m-%d")
    games["temp_mean"] = games["date_str"].map(
        lambda d: weather.get(d, {}).get("temp_mean", 7.5)
    )
    games["temp_max"] = games["date_str"].map(
        lambda d: weather.get(d, {}).get("temp_max", 10.0)
    )
    games["precip_mm"] = games["date_str"].map(
        lambda d: weather.get(d, {}).get("precip_mm", 0.0)
    )
    games["wind_max_kmh"] = games["date_str"].map(
        lambda d: weather.get(d, {}).get("wind_max_kmh", 10.0)
    )

    games["opponent_distance_km"] = games["opponent"].map(OPPONENT_DISTANCE).fillna(0)
    games["opponent_division"] = games["opponent"].map(OPPONENT_DIVISION).fillna("Unknown")

    games["is_weekend"] = games["day_of_week"].isin(["Fri", "Sat", "Sun", "Fir"])
    games["is_holiday"] = False
    holiday_dates = {
        "2024-12-31", "2025-01-01", "2025-02-17", "2025-03-17",
        "2026-01-01", "2026-02-16",
    }
    games["is_holiday"] = games["date_str"].isin(holiday_dates)

    archetypes = {}
    for game_date, group in merged.groupby("game_date"):
        archetypes[game_date] = classify_archetype(group)

    games["archetype"] = games["game_date"].map(archetypes).fillna("mixed")

    game_stats = merged.groupby("game_date").agg(
        total_qty=("Qty", "sum"),
        total_txns=("Qty", "count"),
        unique_items=("Item", "nunique"),
        unique_stands=("stand", "nunique"),
    ).reset_index()

    games = games.merge(game_stats, on="game_date", how="left")

    games["qty_per_cap"] = (
        games["total_qty"] / games["attendance"].replace(0, np.nan)
    ).round(2)

    games = games.drop(columns=["date_str"])
    games.to_parquet(ENRICHED_CACHE, index=False)
    return games
