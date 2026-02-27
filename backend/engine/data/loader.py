"""Load and parse POS transaction CSVs and GameDetails.xlsx."""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path

from engine.config import (
    DATA_DIR, PARQUET_CACHE, GAMES_CACHE, CATEGORY_MAP, SUPER_CATEGORIES,
)


def load_transactions(force_reload: bool = False) -> pd.DataFrame:
    """Load all item CSVs, parse datetimes, add derived fields. Caches to parquet."""
    if PARQUET_CACHE.exists() and not force_reload:
        return pd.read_parquet(PARQUET_CACHE)

    csvs = sorted(DATA_DIR.glob("items-*.csv"))
    frames = [pd.read_csv(f) for f in csvs]
    df = pd.concat(frames, ignore_index=True)

    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
    df["date"] = pd.to_datetime(df["Date"]).dt.date
    df["time"] = pd.to_timedelta(df["Time"])
    df["hour"] = df["datetime"].dt.hour
    df["minute_of_day"] = df["datetime"].dt.hour * 60 + df["datetime"].dt.minute
    df["second_of_day"] = (
        df["datetime"].dt.hour * 3600
        + df["datetime"].dt.minute * 60
        + df["datetime"].dt.second
    )
    df["day_of_week"] = df["datetime"].dt.day_name()
    df["category_norm"] = df["Category"].map(CATEGORY_MAP).fillna("Other")
    df["super_category"] = df["category_norm"].map(SUPER_CATEGORIES).fillna("Other")
    df["stand"] = df["Location"]
    df = df.sort_values("datetime").reset_index(drop=True)
    df.to_parquet(PARQUET_CACHE, index=False)
    return df


def load_games(force_reload: bool = False) -> pd.DataFrame:
    """Parse GameDetails.xlsx handling multi-season headers."""
    if GAMES_CACHE.exists() and not force_reload:
        return pd.read_parquet(GAMES_CACHE)

    import openpyxl
    wb = openpyxl.load_workbook(DATA_DIR / "GameDetails.xlsx")
    ws = wb.active
    rows = list(ws.iter_rows(min_row=1, values_only=True))

    games = []
    current_season = None

    for row in rows:
        _, col_b, col_c, col_d, col_e, col_f, col_g = row

        if col_b == "Event":
            if isinstance(col_d, str) and "Season" in col_d:
                current_season = col_d.split(",")[1].strip() if "," in col_d else col_d
            continue

        if col_b is None and col_d is None:
            continue

        import datetime as dt
        game_date = col_d
        if isinstance(game_date, dt.datetime):
            game_date = game_date.date()

        puck_drop = col_e
        if isinstance(puck_drop, dt.time):
            puck_drop_str = puck_drop.strftime("%H:%M")
        else:
            puck_drop_str = str(puck_drop) if puck_drop else "19:05"

        if current_season == "2024/25 Season" and game_date:
            if game_date.month <= 4 and game_date.year == 2024:
                game_date = game_date.replace(year=2025)

        note = str(col_f).strip() if col_f else ""
        is_playoff = "playoff" in note.lower() if note else False
        is_promo = bool(note) and not is_playoff

        games.append({
            "opponent": col_b,
            "day_of_week": col_c,
            "game_date": game_date,
            "puck_drop": puck_drop_str,
            "note": note,
            "attendance": int(col_g) if col_g else None,
            "season": current_season,
            "is_playoff": is_playoff,
            "is_promo": is_promo,
            "promo_type": note if is_promo else "",
        })

    gdf = pd.DataFrame(games)
    gdf["game_date"] = pd.to_datetime(gdf["game_date"])
    gdf["puck_drop_hour"] = gdf["puck_drop"].apply(
        lambda x: int(x.split(":")[0]) if ":" in str(x) else 19
    )
    gdf["puck_drop_dt"] = pd.to_datetime(
        gdf["game_date"].dt.strftime("%Y-%m-%d") + " " + gdf["puck_drop"]
    )
    gdf.to_parquet(GAMES_CACHE, index=False)
    return gdf


def load_merged(force_reload: bool = False) -> pd.DataFrame:
    """Load transactions with game context joined in."""
    txns = load_transactions(force_reload=force_reload)
    games = load_games(force_reload=force_reload)

    txns["game_date"] = pd.to_datetime(txns["date"])

    merged = txns.merge(
        games[["game_date", "opponent", "attendance", "puck_drop_dt",
               "is_playoff", "is_promo", "promo_type", "season"]],
        on="game_date",
        how="left",
    )

    merged["mins_from_puck_drop"] = (
        (merged["datetime"] - merged["puck_drop_dt"]).dt.total_seconds() / 60
    ).round(1)

    merged["time_window"] = (
        (merged["mins_from_puck_drop"] // 10) * 10
    ).astype("Int64")

    return merged
