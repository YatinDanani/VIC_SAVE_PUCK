"""Learned correction factors from LOO backtest residuals."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd
from pathlib import Path

from engine.config import CACHE_DIR
from engine.data.loader import load_merged
from engine.data.enricher import enrich_games
from engine.data.profiles import build_profiles_from_data
from engine.models.forecast import generate_forecast

CORRECTION_CACHE = CACHE_DIR / "correction_model.json"

FEATURE_NAMES = [
    "attendance_z", "is_weekend", "is_promo", "is_playoff",
    "temp_mean_z", "arch_beer", "arch_family",
    "div_US", "div_BC", "div_East", "puck_drop_hour",
]


def _build_feature_vector(g: pd.Series, att_mean: float, att_std: float,
                          temp_mean: float, temp_std: float) -> list[float]:
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


def load_correction_model() -> dict | None:
    """Load the trained correction model from cache."""
    if not CORRECTION_CACHE.exists():
        return None
    return json.loads(CORRECTION_CACHE.read_text())


def get_correction_factor(game_features: pd.Series, model: dict | None = None) -> float:
    if model is None:
        model = load_correction_model()
    if model is None:
        return 1.0

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
