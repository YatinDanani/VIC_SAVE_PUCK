"""Generate sliding-window prep schedule from forecast output."""

from __future__ import annotations

import pandas as pd
from dataclasses import dataclass

from engine.config import ITEM_PERISHABILITY, STAND_SHORT


@dataclass
class PrepAction:
    time_window: int
    stand: str
    action: str
    item: str
    quantity: int
    tier: str

    @property
    def stand_short(self) -> str:
        return STAND_SHORT.get(self.stand, self.stand)

    def __str__(self) -> str:
        sign = "+" if self.time_window >= 0 else ""
        return (
            f"T{sign}{self.time_window:>4}min | {self.stand_short:<18} | "
            f"{self.action:<16} | {self.item:<22} | qty={self.quantity}"
        )


def generate_prep_plan(forecast: dict) -> list[PrepAction]:
    item_forecast = forecast["item_forecast"]
    actions: list[PrepAction] = []
    qty_col = "prep_qty" if "prep_qty" in item_forecast.columns else "expected_qty"

    for item, group in item_forecast.groupby("item"):
        tier = ITEM_PERISHABILITY.get(item, "medium_hold")
        total_qty = group[qty_col].sum()
        if total_qty <= 0:
            continue

        if tier == "shelf_stable":
            actions.append(PrepAction(
                time_window=-20, stand="ALL", action="pre_stage",
                item=item, quantity=int(total_qty), tier=tier,
            ))
        elif tier == "medium_hold":
            pre_game = group[group["time_window"] < 20][qty_col].sum()
            mid_game = group[(group["time_window"] >= 20) & (group["time_window"] < 58)][qty_col].sum()
            late_game = group[group["time_window"] >= 58][qty_col].sum()

            if pre_game > 0:
                actions.append(PrepAction(time_window=-10, stand="ALL", action="batch", item=item, quantity=int(pre_game), tier=tier))
            if mid_game > 0:
                actions.append(PrepAction(time_window=20, stand="ALL", action="refresh_batch", item=item, quantity=int(mid_game), tier=tier))
            if late_game > 0:
                actions.append(PrepAction(time_window=58, stand="ALL", action="refresh_batch", item=item, quantity=int(late_game), tier=tier))
        elif tier == "short_life":
            for _, row in group.iterrows():
                qty = int(row[qty_col])
                if qty > 0:
                    actions.append(PrepAction(
                        time_window=int(row["time_window"]), stand="ALL",
                        action="continuous_cook", item=item, quantity=qty, tier=tier,
                    ))
            windows = group.sort_values("time_window")
            peak_qty = windows[qty_col].max()
            for _, row in windows.iterrows():
                if row[qty_col] < peak_qty * 0.1 and row["time_window"] > 60:
                    actions.append(PrepAction(
                        time_window=int(row["time_window"]), stand="ALL",
                        action="stop_prep", item=item, quantity=0, tier=tier,
                    ))
                    break

    actions.sort(key=lambda a: a.time_window)
    return actions
