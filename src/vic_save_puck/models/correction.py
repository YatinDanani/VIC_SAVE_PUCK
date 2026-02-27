"""Learned correction factors from LOO backtest residuals."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.progress import track

from vic_save_puck.config import CACHE_DIR
from vic_save_puck.data.loader import load_merged
from vic_save_puck.data.enricher import enrich_games
from vic_save_puck.data.profiles import build_profiles_from_data
from vic_save_puck.models.forecast import generate_forecast

CORRECTION_CACHE = CACHE_DIR / "correction_model.json"

FEATURE_NAMES = [
    "attendance_z", "is_weekend", "is_promo", "is_playoff",
    "temp_mean_z", "arch_beer", "arch_family",
    "div_US", "div_BC", "div_East", "puck_drop_hour",
]


def _build_feature_vector(g: pd.Series, att_mean: float, att_std: float,
                          temp_mean: float, temp_std: float) -> list[float]:
    """Build feature vector from a game row."""
    att_z = (g["attendance"] - att_mean) / att_std if att_std > 0 else 0.0
    temp_z = (g["temp_mean"] - temp_mean) / temp_std if temp_std > 0 else 0.0
    div = g.get("opponent_division", "Unknown")
    return [
        att_z,
        float(g.get("is_weekend", False)),
        float(g.get("is_promo", False)),
        float(g.get("is_playoff", False)),
        temp_z,
        float(g.get("archetype", "") == "beer_crowd"),
        float(g.get("archetype", "") == "family"),
        float(div == "US"),
        float(div == "BC"),
        float(div == "East"),
        float(g.get("puck_drop_hour", 19)),
    ]


def train_correction_model() -> dict:
    """Train correction factors from LOO backtest residuals.

    Returns dict with model coefficients and training metrics.
    """
    console = Console()
    console.print("[cyan]Training correction model from LOO residuals...[/cyan]")

    merged = load_merged()
    games = enrich_games()
    game_dates = sorted(games["game_date"].unique())

    # Collect correction targets and features
    targets = []
    features = []
    game_info_list = []

    att_mean = games["attendance"].mean()
    att_std = games["attendance"].std()
    temp_mean = games["temp_mean"].mean()
    temp_std = games["temp_mean"].std()

    for gd in track(game_dates, description="Computing residuals"):
        gd_ts = pd.Timestamp(gd)
        game_row = games[games["game_date"] == gd_ts]
        if game_row.empty:
            continue
        g = game_row.iloc[0]

        train_merged = merged[merged["game_date"] != gd_ts]
        train_games = games[games["game_date"] != gd_ts]
        if train_merged.empty:
            continue

        profiles = build_profiles_from_data(train_merged, train_games)

        forecast = generate_forecast(
            attendance=int(g["attendance"]),
            puck_drop_hour=int(g["puck_drop_hour"]),
            is_playoff=bool(g["is_playoff"]),
            is_promo=bool(g["is_promo"]),
            promo_type=str(g.get("promo_type", "")),
            temp_mean=float(g.get("temp_mean", 8.0)),
            day_of_week=str(g["day_of_week"]),
            profiles=profiles,
        )

        game_txns = merged[merged["game_date"] == gd_ts]
        actual_total = int(game_txns["Qty"].sum())
        forecast_total = int(forecast["item_forecast"]["expected_qty"].sum())

        if forecast_total <= 0 or actual_total <= 0:
            continue

        correction_target = actual_total / forecast_total
        targets.append(correction_target)
        features.append(_build_feature_vector(g, att_mean, att_std, temp_mean, temp_std))
        game_info_list.append({
            "date": str(gd_ts.date()),
            "actual": actual_total,
            "forecast": forecast_total,
            "correction": round(correction_target, 4),
        })

    X = np.array(features)
    y = np.array(targets)

    # Try sklearn Ridge regression
    model_data: dict = {
        "feature_names": FEATURE_NAMES,
        "feature_stats": {
            "att_mean": att_mean, "att_std": att_std,
            "temp_mean": temp_mean, "temp_std": temp_std,
        },
        "n_games": len(y),
        "mean_correction": float(y.mean()),
        "median_correction": float(np.median(y)),
    }

    try:
        from sklearn.linear_model import Ridge

        ridge = Ridge(alpha=1.0)
        ridge.fit(X, y)

        # LOO predictions for training metrics
        predictions = []
        for i in range(len(X)):
            X_train = np.delete(X, i, axis=0)
            y_train = np.delete(y, i, axis=0)
            r = Ridge(alpha=1.0)
            r.fit(X_train, y_train)
            predictions.append(float(r.predict(X[i:i+1])[0]))

        residuals = y - np.array(predictions)

        model_data.update({
            "method": "ridge",
            "intercept": float(ridge.intercept_),
            "coefficients": [float(c) for c in ridge.coef_],
            "loo_mae": float(np.abs(residuals).mean()),
            "loo_rmse": float(np.sqrt((residuals ** 2).mean())),
            "r2_loo": float(1 - (residuals ** 2).sum() / ((y - y.mean()) ** 2).sum()),
        })

        console.print(f"[green]Ridge model trained[/green] — LOO MAE: {model_data['loo_mae']:.4f}, "
                       f"R2: {model_data['r2_loo']:.3f}")

    except ImportError:
        console.print("[yellow]sklearn not available — using per-archetype mean fallback[/yellow]")

        # Per-archetype mean correction
        arch_corrections = {}
        for i, info in enumerate(game_info_list):
            feat = features[i]
            if feat[5] == 1:
                arch = "beer_crowd"
            elif feat[6] == 1:
                arch = "family"
            else:
                arch = "mixed"
            arch_corrections.setdefault(arch, []).append(targets[i])

        model_data.update({
            "method": "archetype_mean",
            "archetype_corrections": {
                k: float(np.mean(v)) for k, v in arch_corrections.items()
            },
        })

        console.print(f"[green]Archetype mean corrections:[/green]")
        for arch, corr in model_data["archetype_corrections"].items():
            console.print(f"  {arch}: {corr:.3f}")

    # Feature importance (absolute coefficient values)
    if model_data.get("method") == "ridge":
        coefs = model_data["coefficients"]
        importance = sorted(
            zip(FEATURE_NAMES, [abs(c) for c in coefs]),
            key=lambda x: -x[1],
        )
        model_data["feature_importance"] = [
            {"feature": f, "abs_coef": round(c, 4)} for f, c in importance
        ]
        console.print("\n[bold]Feature importance:[/bold]")
        for fi in model_data["feature_importance"][:5]:
            console.print(f"  {fi['feature']}: {fi['abs_coef']:.4f}")

    # Per-game details for analysis
    model_data["game_details"] = game_info_list

    CORRECTION_CACHE.write_text(json.dumps(model_data, indent=2))
    console.print(f"\n[green]Model saved to {CORRECTION_CACHE}[/green]")

    return model_data


def load_correction_model() -> dict | None:
    """Load the trained correction model from cache."""
    if not CORRECTION_CACHE.exists():
        return None
    return json.loads(CORRECTION_CACHE.read_text())


def get_correction_factor(game_features: pd.Series, model: dict | None = None) -> float:
    """Compute correction factor for a game.

    Args:
        game_features: Series with game metadata (attendance, is_weekend, etc.)
        model: Pre-loaded model dict, or None to load from cache.

    Returns:
        Correction multiplier clamped to [0.5, 1.5].
    """
    if model is None:
        model = load_correction_model()
    if model is None:
        return 1.0  # no model available

    if model.get("method") == "ridge":
        stats = model["feature_stats"]
        fv = _build_feature_vector(
            game_features,
            stats["att_mean"], stats["att_std"],
            stats["temp_mean"], stats["temp_std"],
        )
        intercept = model["intercept"]
        coefs = model["coefficients"]
        raw = intercept + sum(c * f for c, f in zip(coefs, fv))
    elif model.get("method") == "archetype_mean":
        arch = game_features.get("archetype", "mixed")
        arch_corr = model.get("archetype_corrections", {})
        raw = arch_corr.get(arch, model.get("mean_correction", 1.0))
    else:
        raw = model.get("mean_correction", 1.0)

    return float(np.clip(raw, 0.5, 1.5))
