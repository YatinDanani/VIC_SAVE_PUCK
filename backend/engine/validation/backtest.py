"""Leave-one-out cross-validation for the forecast model."""

from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass

from engine.data.loader import load_merged
from engine.data.enricher import enrich_games
from engine.data.profiles import build_profiles_from_data
from engine.models.forecast import generate_forecast


@dataclass
class GameResult:
    game_date: pd.Timestamp
    opponent: str
    attendance: int
    archetype: str
    actual_total: int
    forecast_total: int
    volume_error: float
    stand_mape: float
    item_mape: float
    prep_coverage: float
    waste_units: int
    stockout_units: int

    def to_dict(self) -> dict:
        return {
            "game_date": str(self.game_date.date()),
            "opponent": self.opponent,
            "attendance": self.attendance,
            "archetype": self.archetype,
            "actual_total": self.actual_total,
            "forecast_total": self.forecast_total,
            "volume_error": round(self.volume_error, 4),
            "volume_error_pct": f"{self.volume_error:+.1%}",
            "stand_mape": round(self.stand_mape, 4),
            "item_mape": round(self.item_mape, 4),
            "prep_coverage": round(self.prep_coverage, 4),
            "waste_units": self.waste_units,
            "stockout_units": self.stockout_units,
        }


def run_backtest(use_correction: bool = False) -> list[GameResult]:
    """Run leave-one-out cross-validation over all games."""
    merged = load_merged()
    games = enrich_games()

    correction_model = None
    if use_correction:
        from engine.models.correction import load_correction_model
        correction_model = load_correction_model()

    game_dates = sorted(games["game_date"].unique())
    results: list[GameResult] = []

    for gd in game_dates:
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

        if correction_model is not None:
            from engine.models.correction import get_correction_factor
            cf = get_correction_factor(g, model=correction_model)
            forecast["item_forecast"]["expected_qty"] = (
                forecast["item_forecast"]["expected_qty"] * cf
            ).round(0).astype(int)
            forecast["item_forecast"]["prep_qty"] = (
                forecast["item_forecast"]["prep_qty"] * cf
            ).round(0).astype(int)

        game_txns = merged[merged["game_date"] == gd_ts]
        actual_total = int(game_txns["Qty"].sum())

        item_fc = forecast["item_forecast"]
        forecast_total = int(item_fc["expected_qty"].sum())
        volume_error = (
            (forecast_total - actual_total) / actual_total
            if actual_total > 0 else 0.0
        )

        stand_fc = forecast["stand_forecast"]
        actual_by_stand = (
            game_txns.groupby("stand")["Qty"].sum().reset_index()
            .rename(columns={"Qty": "actual_qty"})
        )
        stand_comp = stand_fc.groupby("stand")["expected_qty"].sum().reset_index()
        stand_comp = stand_comp.merge(actual_by_stand, on="stand", how="inner")
        if not stand_comp.empty and (stand_comp["actual_qty"] > 0).any():
            mask = stand_comp["actual_qty"] > 0
            stand_mape = (
                (stand_comp.loc[mask, "expected_qty"] - stand_comp.loc[mask, "actual_qty"]).abs()
                / stand_comp.loc[mask, "actual_qty"]
            ).mean()
        else:
            stand_mape = 0.0

        actual_by_item = (
            game_txns.groupby("Item")["Qty"].sum()
            .sort_values(ascending=False)
            .head(15)
            .reset_index()
            .rename(columns={"Qty": "actual_qty"})
        )
        item_comp = item_fc.groupby("item")["expected_qty"].sum().reset_index()
        item_comp = item_comp.merge(
            actual_by_item, left_on="item", right_on="Item", how="inner"
        )
        if not item_comp.empty and (item_comp["actual_qty"] > 0).any():
            mask = item_comp["actual_qty"] > 0
            item_mape = (
                (item_comp.loc[mask, "expected_qty"] - item_comp.loc[mask, "actual_qty"]).abs()
                / item_comp.loc[mask, "actual_qty"]
            ).mean()
        else:
            item_mape = 0.0

        prep_fc = item_fc.groupby("item")[["prep_qty", "expected_qty"]].sum().reset_index()
        actual_items = (
            game_txns.groupby("Item")["Qty"].sum().reset_index()
            .rename(columns={"Item": "item", "Qty": "actual_qty"})
        )
        prep_comp = prep_fc.merge(actual_items, on="item", how="outer").fillna(0)

        covered = (prep_comp["prep_qty"] >= prep_comp["actual_qty"]).sum()
        total_items = len(prep_comp[prep_comp["actual_qty"] > 0])
        prep_coverage = covered / total_items if total_items > 0 else 1.0

        waste_units = int(
            prep_comp.apply(lambda r: max(0, r["prep_qty"] - r["actual_qty"]), axis=1).sum()
        )
        stockout_units = int(
            prep_comp.apply(lambda r: max(0, r["actual_qty"] - r["prep_qty"]), axis=1).sum()
        )

        results.append(GameResult(
            game_date=gd_ts,
            opponent=str(g["opponent"]),
            attendance=int(g["attendance"]),
            archetype=str(g["archetype"]),
            actual_total=actual_total,
            forecast_total=forecast_total,
            volume_error=volume_error,
            stand_mape=stand_mape,
            item_mape=item_mape,
            prep_coverage=prep_coverage,
            waste_units=waste_units,
            stockout_units=stockout_units,
        ))

    return results
