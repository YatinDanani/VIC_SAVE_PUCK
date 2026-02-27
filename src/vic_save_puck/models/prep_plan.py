"""Generate sliding-window prep schedule from forecast output."""

from __future__ import annotations

import pandas as pd
from dataclasses import dataclass

from vic_save_puck.config import ITEM_PERISHABILITY, STAND_SHORT


@dataclass
class PrepAction:
    """A single prep action for a stand."""
    time_window: int        # minutes from puck drop
    stand: str
    action: str             # "pre_stage", "batch", "continuous_cook", "stop_prep"
    item: str
    quantity: int
    tier: str               # "shelf_stable", "medium_hold", "short_life"

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
    """
    Convert forecast into a time-ordered prep plan.

    Strategy per perishability tier:
    - shelf_stable: pre-stage everything at T-20min (before doors open)
    - medium_hold: batch at T-10min, refresh at intermissions (T+20, T+58)
    - short_life: continuous cook per window, stop when demand drops below threshold
    """
    item_forecast = forecast["item_forecast"]
    stand_forecast = forecast["stand_forecast"]

    actions: list[PrepAction] = []

    # Use prep_qty (conservative target) instead of expected_qty (full demand)
    qty_col = "prep_qty" if "prep_qty" in item_forecast.columns else "expected_qty"

    # Group item forecast by item
    for item, group in item_forecast.groupby("item"):
        tier = ITEM_PERISHABILITY.get(item, "medium_hold")
        total_qty = group[qty_col].sum()
        if total_qty <= 0:
            continue

        if tier == "shelf_stable":
            # Pre-stage full game quantity at T-20
            actions.append(PrepAction(
                time_window=-20,
                stand="ALL",
                action="pre_stage",
                item=item,
                quantity=int(total_qty),
                tier=tier,
            ))

        elif tier == "medium_hold":
            # Batch before game, refresh at intermissions
            pre_game = group[group["time_window"] < 20][qty_col].sum()
            mid_game = group[
                (group["time_window"] >= 20) & (group["time_window"] < 58)
            ][qty_col].sum()
            late_game = group[group["time_window"] >= 58][qty_col].sum()

            if pre_game > 0:
                actions.append(PrepAction(
                    time_window=-10,
                    stand="ALL",
                    action="batch",
                    item=item,
                    quantity=int(pre_game),
                    tier=tier,
                ))
            if mid_game > 0:
                actions.append(PrepAction(
                    time_window=20,
                    stand="ALL",
                    action="refresh_batch",
                    item=item,
                    quantity=int(mid_game),
                    tier=tier,
                ))
            if late_game > 0:
                actions.append(PrepAction(
                    time_window=58,
                    stand="ALL",
                    action="refresh_batch",
                    item=item,
                    quantity=int(late_game),
                    tier=tier,
                ))

        elif tier == "short_life":
            # Continuous cook per time window
            for _, row in group.iterrows():
                qty = int(row[qty_col])
                if qty > 0:
                    actions.append(PrepAction(
                        time_window=int(row["time_window"]),
                        stand="ALL",
                        action="continuous_cook",
                        item=item,
                        quantity=qty,
                        tier=tier,
                    ))

            # Add stop-prep signal when demand drops
            windows = group.sort_values("time_window")
            peak_qty = windows[qty_col].max()
            for _, row in windows.iterrows():
                if row[qty_col] < peak_qty * 0.1 and row["time_window"] > 60:
                    actions.append(PrepAction(
                        time_window=int(row["time_window"]),
                        stand="ALL",
                        action="stop_prep",
                        item=item,
                        quantity=0,
                        tier=tier,
                    ))
                    break

    # Sort by time
    actions.sort(key=lambda a: a.time_window)
    return actions


def format_prep_plan(actions: list[PrepAction]) -> str:
    """Format prep plan as a readable table."""
    lines = ["=" * 90]
    lines.append(f"{'Time':>10} | {'Stand':<18} | {'Action':<16} | {'Item':<22} | Qty")
    lines.append("-" * 90)
    for a in actions:
        lines.append(str(a))
    lines.append("=" * 90)
    return "\n".join(lines)
