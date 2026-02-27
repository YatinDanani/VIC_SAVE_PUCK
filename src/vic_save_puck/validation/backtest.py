"""Leave-one-out cross-validation for the forecast model."""

from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich import box

from vic_save_puck.data.loader import load_merged
from vic_save_puck.data.enricher import enrich_games
from vic_save_puck.data.profiles import build_profiles_from_data
from vic_save_puck.models.forecast import generate_forecast


@dataclass
class GameResult:
    """Validation result for a single held-out game."""
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


def run_backtest(detailed: bool = False, use_correction: bool = False) -> list[GameResult]:
    """Run leave-one-out cross-validation over all games.

    Args:
        detailed: Show per-game results table.
        use_correction: Apply learned correction factors to forecasts.
    """
    console = Console()

    console.print("[cyan]Loading data...[/cyan]")
    merged = load_merged()
    games = enrich_games()

    # Load correction model if requested
    correction_model = None
    if use_correction:
        from vic_save_puck.models.correction import load_correction_model
        correction_model = load_correction_model()
        if correction_model is None:
            console.print("[yellow]No correction model found. Run --train-correction first.[/yellow]")
            console.print("[yellow]Proceeding without correction.[/yellow]")
        else:
            console.print(f"[green]Correction model loaded ({correction_model['method']}, "
                          f"n={correction_model['n_games']})[/green]")

    game_dates = sorted(games["game_date"].unique())
    label = "LOO validation" + (" + correction" if correction_model else "")
    console.print(f"Running {label} over {len(game_dates)} games\n")

    results: list[GameResult] = []

    for gd in track(game_dates, description="Backtesting"):
        gd_ts = pd.Timestamp(gd)

        # ── Get game info ─────────────────────────────────────────────
        game_row = games[games["game_date"] == gd_ts]
        if game_row.empty:
            continue
        g = game_row.iloc[0]

        # ── Hold out this game's transactions ─────────────────────────
        train_merged = merged[merged["game_date"] != gd_ts]
        train_games = games[games["game_date"] != gd_ts]

        if train_merged.empty:
            continue

        # ── Build profiles from remaining games ───────────────────────
        profiles = build_profiles_from_data(train_merged, train_games)

        # ── Generate forecast for held-out game ───────────────────────
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

        # ── Apply correction factor if available ────────────────────────
        if correction_model is not None:
            from vic_save_puck.models.correction import get_correction_factor
            cf = get_correction_factor(g, model=correction_model)
            forecast["item_forecast"]["expected_qty"] = (
                forecast["item_forecast"]["expected_qty"] * cf
            ).round(0).astype(int)
            forecast["item_forecast"]["prep_qty"] = (
                forecast["item_forecast"]["prep_qty"] * cf
            ).round(0).astype(int)
            if "stand_forecast" in forecast:
                forecast["stand_forecast"]["expected_qty"] = (
                    forecast["stand_forecast"]["expected_qty"] * cf
                ).round(0).astype(int)

        # ── Actuals for this game ─────────────────────────────────────
        game_txns = merged[merged["game_date"] == gd_ts]
        actual_total = int(game_txns["Qty"].sum())

        # ── Overall volume error ──────────────────────────────────────
        item_fc = forecast["item_forecast"]
        forecast_total = int(item_fc["expected_qty"].sum())
        volume_error = (
            (forecast_total - actual_total) / actual_total
            if actual_total > 0 else 0.0
        )

        # ── Stand MAPE ────────────────────────────────────────────────
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

        # ── Item MAPE (top items by actual volume) ────────────────────
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

        # ── Prep metrics ──────────────────────────────────────────────
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
            prep_comp.apply(
                lambda r: max(0, r["prep_qty"] - r["actual_qty"]), axis=1
            ).sum()
        )
        stockout_units = int(
            prep_comp.apply(
                lambda r: max(0, r["actual_qty"] - r["prep_qty"]), axis=1
            ).sum()
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

    console.print()
    format_backtest_results(results, detailed=detailed)
    return results


def format_backtest_results(results: list[GameResult], detailed: bool = False) -> None:
    """Print formatted backtest results."""
    console = Console()

    if not results:
        console.print("[red]No results to display[/red]")
        return

    df = pd.DataFrame([vars(r) for r in results])

    # ── Summary table ─────────────────────────────────────────────────
    table = Table(
        title="LOO Cross-Validation Summary",
        box=box.ROUNDED,
    )
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    n = len(df)
    table.add_row("Games validated", str(n))
    table.add_row("Median volume error", f"{df['volume_error'].median():+.1%}")
    table.add_row("Mean abs volume error", f"{df['volume_error'].abs().mean():.1%}")
    table.add_row("Mean stand MAPE", f"{df['stand_mape'].mean():.1%}")
    table.add_row("Mean item MAPE", f"{df['item_mape'].mean():.1%}")
    table.add_row("Median stand MAPE", f"{df['stand_mape'].median():.1%}")
    table.add_row("Median item MAPE", f"{df['item_mape'].median():.1%}")

    within_15 = (df["volume_error"].abs() <= 0.15).sum()
    table.add_row("Games within +/-15%", f"{within_15}/{n} ({within_15/n:.0%})")

    within_25 = (df["volume_error"].abs() <= 0.25).sum()
    table.add_row("Games within +/-25%", f"{within_25}/{n} ({within_25/n:.0%})")

    console.print(table)

    # ── By archetype ──────────────────────────────────────────────────
    arch_table = Table(
        title="Results by Archetype",
        box=box.ROUNDED,
    )
    arch_table.add_column("Archetype", style="bold")
    arch_table.add_column("Count", justify="right")
    arch_table.add_column("Med Vol Err", justify="right")
    arch_table.add_column("Mean Stand MAPE", justify="right")
    arch_table.add_column("Mean Item MAPE", justify="right")
    arch_table.add_column("Within 15%", justify="right")

    for arch in sorted(df["archetype"].unique()):
        sub = df[df["archetype"] == arch]
        w15 = (sub["volume_error"].abs() <= 0.15).sum()
        arch_table.add_row(
            arch,
            str(len(sub)),
            f"{sub['volume_error'].median():+.1%}",
            f"{sub['stand_mape'].mean():.1%}",
            f"{sub['item_mape'].mean():.1%}",
            f"{w15}/{len(sub)}",
        )

    console.print(arch_table)

    # ── Prep analysis ─────────────────────────────────────────────────
    prep_table = Table(
        title="Prep Plan Analysis",
        box=box.ROUNDED,
    )
    prep_table.add_column("Metric", style="bold")
    prep_table.add_column("Value", justify="right")

    prep_table.add_row("Mean prep coverage", f"{df['prep_coverage'].mean():.1%}")
    prep_table.add_row("Median prep coverage", f"{df['prep_coverage'].median():.1%}")

    total_waste = df["waste_units"].sum()
    total_stockout = df["stockout_units"].sum()
    total_actual = df["actual_total"].sum()
    prep_table.add_row("Total waste units", f"{total_waste:,}")
    prep_table.add_row("Total stockout units", f"{total_stockout:,}")
    prep_table.add_row("Waste rate (vs actual)", f"{total_waste / total_actual:.1%}")
    prep_table.add_row("Stockout rate (vs actual)", f"{total_stockout / total_actual:.1%}")

    console.print(prep_table)

    # ── Best / Worst games ────────────────────────────────────────────
    df_sorted = df.sort_values("volume_error", key=abs)
    bw_table = Table(title="Best & Worst Predicted Games", box=box.ROUNDED)
    bw_table.add_column("Rank", style="bold")
    bw_table.add_column("Date")
    bw_table.add_column("Opponent")
    bw_table.add_column("Arch")
    bw_table.add_column("Attend", justify="right")
    bw_table.add_column("Vol Err", justify="right")
    bw_table.add_column("Stand MAPE", justify="right")

    for i, (_, row) in enumerate(df_sorted.head(5).iterrows()):
        bw_table.add_row(
            f"Best {i+1}",
            str(row["game_date"].date()),
            row["opponent"],
            row["archetype"],
            f"{row['attendance']:,}",
            f"{row['volume_error']:+.1%}",
            f"{row['stand_mape']:.1%}",
        )

    for i, (_, row) in enumerate(df_sorted.tail(5).iloc[::-1].iterrows()):
        bw_table.add_row(
            f"Worst {i+1}",
            str(row["game_date"].date()),
            row["opponent"],
            row["archetype"],
            f"{row['attendance']:,}",
            f"{row['volume_error']:+.1%}",
            f"{row['stand_mape']:.1%}",
        )

    console.print(bw_table)

    # ── Detailed per-game table ───────────────────────────────────────
    if detailed:
        det_table = Table(title="Per-Game Results", box=box.SIMPLE)
        det_table.add_column("Date")
        det_table.add_column("Opp")
        det_table.add_column("Arch")
        det_table.add_column("Actual", justify="right")
        det_table.add_column("Forecast", justify="right")
        det_table.add_column("Vol Err", justify="right")
        det_table.add_column("St MAPE", justify="right")
        det_table.add_column("It MAPE", justify="right")
        det_table.add_column("Prep Cov", justify="right")

        for _, row in df.sort_values("game_date").iterrows():
            err_color = "green" if abs(row["volume_error"]) <= 0.15 else (
                "yellow" if abs(row["volume_error"]) <= 0.25 else "red"
            )
            det_table.add_row(
                str(row["game_date"].date()),
                row["opponent"][:12],
                row["archetype"][:6],
                f"{row['actual_total']:,}",
                f"{row['forecast_total']:,}",
                f"[{err_color}]{row['volume_error']:+.1%}[/{err_color}]",
                f"{row['stand_mape']:.1%}",
                f"{row['item_mape']:.1%}",
                f"{row['prep_coverage']:.0%}",
            )

        console.print(det_table)
