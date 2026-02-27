"""CLI demo runner: forecast → simulator → drift engine → AI reasoning → post-game report."""

from __future__ import annotations

import argparse
import time
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.columns import Columns
from rich import box

from vic_save_puck.config import STAND_SHORT
from vic_save_puck.data.profiles import build_profiles
from vic_save_puck.models.forecast import forecast_for_game, generate_forecast
from vic_save_puck.models.prep_plan import generate_prep_plan, format_prep_plan
from vic_save_puck.models.drift import DriftDetector
from vic_save_puck.simulator.engine import GameSimulator, GameEvent
from vic_save_puck.simulator.scenarios import get_scenarios, list_scenarios
from vic_save_puck.ai.reasoning import analyze_drift, ReasoningResult
from vic_save_puck.ai.post_game import generate_post_game_report
from vic_save_puck.ai.event_optimizer import analyze_promo_opportunities, generate_ai_event_recommendations
from vic_save_puck.models.traffic_light import TrafficLightMonitor, Status
from vic_save_puck.validation.backtest import run_backtest

console = Console()


def run_demo(
    scenario_key: str = "normal",
    speed: float = 60.0,
    skip_ai: bool = False,
):
    """Run the full demo pipeline."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]VIC SAVE PUCK[/bold cyan]\n"
        "[dim]Real-time Adaptive F&B Prep Optimization[/dim]\n"
        "[dim]Save on Foods Memorial Centre — Victoria Royals (WHL)[/dim]",
        border_style="cyan",
    ))
    console.print()

    # ── Load scenario ────────────────────────────────────────────────────
    scenarios = get_scenarios()
    if scenario_key not in scenarios:
        console.print(f"[red]Unknown scenario: {scenario_key}[/red]")
        console.print(f"Available: {', '.join(scenarios.keys())}")
        return

    scenario = scenarios[scenario_key]
    console.print(f"[bold]Scenario:[/bold] {scenario.name}")
    console.print(f"[dim]{scenario.description}[/dim]")
    console.print(f"[bold]Game date:[/bold] {scenario.game_date}")
    console.print(f"[bold]Speed:[/bold] {speed}x")
    console.print()

    # ── Phase 1: Build profiles ──────────────────────────────────────────
    with console.status("[cyan]Loading historical profiles..."):
        profiles = build_profiles()
    console.print("[green]✓[/green] Historical profiles loaded")

    # ── Phase 2: Generate forecast ───────────────────────────────────────
    with console.status("[cyan]Generating pre-game forecast..."):
        forecast = forecast_for_game(scenario.game_date, profiles=profiles)

    console.print(f"[green]✓[/green] Forecast generated: archetype=[bold]{forecast['archetype']}[/bold], "
                  f"scale={forecast['scale_factor']}, beer_adj={forecast['beer_factor']}")

    # Show forecast summary with prep targets
    item_fc = forecast["item_forecast"]
    top_items_df = (
        item_fc.groupby("item")[["expected_qty", "prep_qty"]]
        .sum()
        .sort_values("expected_qty", ascending=False)
        .head(8)
    )

    table = Table(title="Top 8 Forecasted Items (Asymmetric Prep)", box=box.SIMPLE)
    table.add_column("Item", style="bold")
    table.add_column("Forecast", justify="right")
    table.add_column("Prep Qty", justify="right", style="cyan")
    table.add_column("Target %", justify="right", style="dim")
    for item, row in top_items_df.iterrows():
        pct = row["prep_qty"] / row["expected_qty"] * 100 if row["expected_qty"] > 0 else 0
        table.add_row(item, str(int(row["expected_qty"])), str(int(row["prep_qty"])), f"{pct:.0f}%")
    console.print(table)

    total_exp = item_fc["expected_qty"].sum()
    total_prep = item_fc["prep_qty"].sum()
    console.print(f"  [dim]Total: {total_exp:,} forecast → {total_prep:,} prep ({total_prep/total_exp:.1%}) — deliberate underprediction to minimize waste[/dim]")

    # ── Phase 2b: Prep plan ──────────────────────────────────────────────
    with console.status("[cyan]Generating prep plan..."):
        prep_actions = generate_prep_plan(forecast)

    console.print(f"[green]✓[/green] Prep plan: {len(prep_actions)} actions")
    # Show first few prep actions
    for a in prep_actions[:5]:
        console.print(f"  [dim]{a}[/dim]")
    if len(prep_actions) > 5:
        console.print(f"  [dim]... and {len(prep_actions) - 5} more[/dim]")
    console.print()

    # ── Phase 3: Initialize simulator ────────────────────────────────────
    sim = scenario.build_simulator(speed=speed)
    game_info = sim.game_info
    console.print(Panel(
        f"[bold]vs {game_info['opponent']}[/bold] | "
        f"Attendance: {game_info['attendance']:,} | "
        f"Archetype: {game_info['archetype']} | "
        f"Transactions: {game_info['total_transactions']:,}",
        title="[bold yellow]GAME START[/bold yellow]",
        border_style="yellow",
    ))
    console.print()

    # ── Phase 4: Run simulation with drift detection ─────────────────────
    detector = DriftDetector(forecast)
    traffic_monitor = TrafficLightMonitor(detector)
    reasoning_results: list[ReasoningResult] = []
    current_window = None
    event_count = 0
    window_event_buffer: list[GameEvent] = []

    def on_window_complete(tw: int, events: list[GameEvent]):
        """Called when a time window completes."""
        nonlocal reasoning_results

        report = detector.check_drift(tw)
        status = traffic_monitor.update(tw)

        actual = sum(e.qty for e in events)

        # Always show traffic light status line
        status_color = {"green": "green", "yellow": "yellow", "red": "red"}[status.overall_status.value]
        status_line = traffic_monitor.summary_line()
        console.print(f"  [{status_color}]{status_line}[/{status_color}]")

        if not report.has_significant_drift:
            return

        # Show detailed stand statuses for yellow/red windows
        if status.overall_status in (Status.YELLOW, Status.RED):
            for ss in status.stand_statuses:
                if ss.status != Status.GREEN:
                    ss_color = "red" if ss.status == Status.RED else "yellow"
                    console.print(f"    [{ss_color}]{ss}[/{ss_color}]")

        # Significant drift: show drift panel
        severity_color = "red" if any(s.severity == "critical" for s in report.signals) else "yellow"

        console.print()
        console.print(Panel(
            _format_drift_panel(report, actual),
            title=f"[bold {severity_color}]DRIFT DETECTED T{tw:+}min[/bold {severity_color}]",
            border_style=severity_color,
        ))

        # AI reasoning only for RED status (saves API calls, focuses on actionable)
        if not skip_ai and status.overall_status == Status.RED:
            with console.status("[cyan]AI analyzing drift..."):
                result = analyze_drift(
                    drift_report=report,
                    game_context=game_info,
                    cumulative_drift=detector.cumulative_drift(),
                    recent_reports=detector.history[-5:],
                )
            reasoning_results.append(result)

            cause_color = {
                "volume_surge": "red",
                "volume_drop": "blue",
                "untagged_promo": "magenta",
                "stand_redistribution": "yellow",
                "weather_effect": "cyan",
                "noise": "dim",
            }.get(result.cause, "white")

            console.print(Panel(
                f"[bold]Cause:[/bold] [{cause_color}]{result.cause}[/{cause_color}] "
                f"(confidence: {result.confidence:.0%})\n\n"
                f"[bold]Alert:[/bold] {result.alert_text}\n\n"
                f"[bold]Actions:[/bold] {_format_actions(result.actions)}",
                title="[bold cyan]AI RECOMMENDATION[/bold cyan]",
                border_style="cyan",
            ))
        console.print()

    # Run simulation in batch mode (events emitted instantly)
    # but process window-by-window
    console.print("[bold]Running game simulation...[/bold]")
    console.print()

    events = []
    window_buffers: dict[int, list[GameEvent]] = {}

    # Batch run for speed
    all_events = sim.run_batch()

    # Process events window by window
    processed_windows = set()
    for event in all_events:
        detector.ingest_event(event)
        tw = event.time_window

        if tw not in window_buffers:
            window_buffers[tw] = []
        window_buffers[tw].append(event)

    # Process windows in order
    for tw in sorted(window_buffers.keys()):
        on_window_complete(tw, window_buffers[tw])

    # ── Phase 5: Post-game report ────────────────────────────────────────
    console.print()
    console.print(Panel.fit(
        "[bold]GAME COMPLETE[/bold]",
        border_style="green",
    ))

    summary = detector.summary()
    summary_table = Table(title="Game Summary", box=box.ROUNDED)
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Total Forecast", f"{summary['total_forecast']:,}")
    summary_table.add_row("Total Actual", f"{summary['total_actual']:,}")
    summary_table.add_row("Cumulative Drift", summary["cumulative_drift"])
    summary_table.add_row("Drift Windows", f"{summary['windows_with_drift']}/{summary['total_windows']}")
    summary_table.add_row("Critical Signals", str(summary["critical_signals"]))
    summary_table.add_row("AI Interventions", str(len(reasoning_results)))
    console.print(summary_table)

    if not skip_ai:
        console.print()
        with console.status("[cyan]AI generating post-game report..."):
            report = generate_post_game_report(
                game_context=game_info,
                drift_detector=detector,
                reasoning_results=reasoning_results,
                forecast=forecast,
            )
        console.print(Panel(
            report,
            title="[bold green]POST-GAME AI ANALYSIS[/bold green]",
            border_style="green",
        ))
    console.print()


def _format_drift_panel(report, actual: int) -> str:
    """Format drift report for display."""
    lines = [f"Total: {actual} units | Overall: {report.overall_volume_drift:+.0%}"]

    # Stand drifts
    stand_lines = []
    for stand, drift in sorted(report.stand_drifts.items(), key=lambda x: -abs(x[1])):
        if abs(drift) >= 0.15:
            short = STAND_SHORT.get(stand, stand)
            color = "red" if drift > 0.2 else ("blue" if drift < -0.2 else "yellow")
            stand_lines.append(f"  [{color}]{short}: {drift:+.0%}[/{color}]")
    if stand_lines:
        lines.append("\n[bold]Stands:[/bold]")
        lines.extend(stand_lines[:5])

    # Top item signals
    item_signals = [s for s in report.signals if s.drift_type == "mix"][:5]
    if item_signals:
        lines.append("\n[bold]Items:[/bold]")
        for s in item_signals:
            color = "red" if s.magnitude > 0 else "blue"
            lines.append(f"  [{color}]{s.scope}: {s.magnitude:+.0%}[/{color}]")

    return "\n".join(lines)


def _format_actions(actions: list[dict]) -> str:
    """Format AI actions for display."""
    if not actions:
        return "[dim]No specific prep changes recommended[/dim]"
    lines = []
    for a in actions[:5]:
        lines.append(
            f"  • {a.get('stand', 'ALL')}: {a.get('action', '?')} "
            f"{a.get('item', '')} ({a.get('quantity_change_pct', 0):+}%)"
        )
    return "\n".join(lines)


def run_event_optimizer(skip_ai: bool = False):
    """Run the promo/event optimization analysis."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]VIC SAVE PUCK — Event Optimizer[/bold cyan]\n"
        "[dim]Data-driven promo, event, and early-bird recommendations[/dim]",
        border_style="cyan",
    ))
    console.print()

    with console.status("[cyan]Analyzing historical patterns..."):
        recommendations = analyze_promo_opportunities()

    console.print(f"[green]✓[/green] Found {len(recommendations)} insights\n")

    for r in recommendations:
        color = {"promo": "magenta", "early_bird": "yellow", "event": "cyan", "scheduling": "green"}.get(
            r.recommendation_type, "white"
        )
        console.print(Panel(
            f"[bold]Impact:[/bold] {r.expected_impact}\n"
            f"[bold]Confidence:[/bold] {r.confidence:.0%}\n"
            f"[bold]Rationale:[/bold] {r.rationale}",
            title=f"[bold {color}]{r.recommendation_type.upper()}: {r.description}[/bold {color}]",
            border_style=color,
        ))

    if not skip_ai:
        console.print()
        with console.status("[cyan]AI synthesizing strategic recommendations..."):
            ai_report = generate_ai_event_recommendations(recommendations)
        console.print(Panel(
            ai_report,
            title="[bold green]AI STRATEGIC RECOMMENDATIONS[/bold green]",
            border_style="green",
        ))


def main():
    parser = argparse.ArgumentParser(description="VIC SAVE PUCK — F&B Optimization Demo")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Game simulation command (default)
    sim_parser = subparsers.add_parser("sim", help="Run game simulation")
    sim_parser.add_argument(
        "--scenario", "-s",
        choices=["normal", "untagged_promo", "stand_redistribution", "weather_surprise", "playoff"],
        default="normal",
        help="Demo scenario to run",
    )
    sim_parser.add_argument(
        "--speed", "-x",
        type=float,
        default=60.0,
        help="Simulation speed multiplier (default: 60x)",
    )
    sim_parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI reasoning (for testing without API key)",
    )
    sim_parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List available scenarios and exit",
    )

    # Backtest command
    bt_parser = subparsers.add_parser("backtest", help="Run LOO cross-validation backtest")
    bt_parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show per-game results table",
    )
    bt_parser.add_argument(
        "--train-correction",
        action="store_true",
        help="Train correction model from LOO residuals",
    )
    bt_parser.add_argument(
        "--with-correction",
        action="store_true",
        help="Apply learned correction factors during backtest",
    )
    bt_parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run Claude AI error analysis after backtest",
    )
    bt_parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI analysis (use rule-based fallback)",
    )

    # Web dashboard command
    web_parser = subparsers.add_parser("web", help="Launch web dashboard")
    web_parser.add_argument("--port", type=int, default=5050, help="Port (default: 5050)")
    web_parser.add_argument("--debug", action="store_true", help="Flask debug mode")
    web_parser.add_argument("--skip-ai", action="store_true", help="Skip AI reasoning")

    # Event optimizer command
    event_parser = subparsers.add_parser("events", help="Run event/promo optimizer")
    event_parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI synthesis",
    )

    args = parser.parse_args()

    if args.command == "web":
        from vic_save_puck.web.app import create_app, socketio
        app = create_app(skip_ai=args.skip_ai, debug=args.debug)
        console.print(Panel.fit(
            f"[bold cyan]VIC SAVE PUCK — Web Dashboard[/bold cyan]\n"
            f"[dim]Open http://localhost:{args.port} in your browser[/dim]",
            border_style="cyan",
        ))
        socketio.run(app, host="0.0.0.0", port=args.port, debug=args.debug, allow_unsafe_werkzeug=True)
        return
    elif args.command == "backtest":
        if args.train_correction:
            from vic_save_puck.models.correction import train_correction_model
            train_correction_model()
            console.print()

        results = run_backtest(detailed=args.detailed, use_correction=args.with_correction)

        if args.analyze and not args.skip_ai:
            from vic_save_puck.ai.forecast_analyst import analyze_forecast_errors
            from vic_save_puck.data.enricher import enrich_games as _enrich
            console.print()
            with console.status("[cyan]AI analyzing forecast errors..."):
                analysis = analyze_forecast_errors(results, games=_enrich())
            console.print(Panel(
                f"[bold]Summary:[/bold] {analysis.summary}\n",
                title="[bold green]AI FORECAST ERROR ANALYSIS[/bold green]",
                border_style="green",
            ))
            if analysis.key_findings:
                console.print("[bold]Key Findings:[/bold]")
                for f in analysis.key_findings:
                    console.print(f"  [cyan]\u2022[/cyan] {f}")
                console.print()
            if analysis.feature_importance:
                console.print("[bold]Feature Importance:[/bold]")
                for feat, desc in analysis.feature_importance.items():
                    console.print(f"  [yellow]{feat}[/yellow]: {desc}")
                console.print()
            if analysis.threshold_recommendations:
                console.print("[bold]Threshold Recommendations:[/bold]")
                for rec in analysis.threshold_recommendations:
                    console.print(f"  [magenta]{rec.get('parameter', '?')}[/magenta]: "
                                  f"{rec.get('current', '?')} \u2192 {rec.get('recommended', '?')} "
                                  f"({rec.get('rationale', '')})")
                console.print()
            if analysis.outlier_explanations:
                console.print("[bold]Outlier Explanations:[/bold]")
                for out in analysis.outlier_explanations[:5]:
                    console.print(f"  [red]{out.get('game', '?')}[/red] ({out.get('error', '?')}): "
                                  f"{out.get('likely_cause', '')}")
                console.print()
        elif args.analyze and args.skip_ai:
            from vic_save_puck.ai.forecast_analyst import _fallback_analysis
            import pandas as _pd
            df = _pd.DataFrame([vars(r) for r in results])
            analysis = _fallback_analysis(df, "skipped by user")
            console.print()
            console.print(Panel(
                f"[bold]Summary:[/bold] {analysis.summary}",
                title="[bold yellow]RULE-BASED FORECAST ANALYSIS[/bold yellow]",
                border_style="yellow",
            ))
            if analysis.key_findings:
                for f in analysis.key_findings:
                    console.print(f"  [cyan]\u2022[/cyan] {f}")
    elif args.command == "events":
        run_event_optimizer(skip_ai=args.skip_ai)
    elif args.command == "sim":
        if args.list_scenarios:
            for s in list_scenarios():
                console.print(f"[bold]{s['key']:20}[/bold] | {s['game_date']} | {s['name']}")
                console.print(f"  [dim]{s['description']}[/dim]")
            return
        run_demo(
            scenario_key=args.scenario,
            speed=args.speed,
            skip_ai=args.skip_ai,
        )
    else:
        # Default to sim if no command given
        run_demo(skip_ai="--skip-ai" in sys.argv)


if __name__ == "__main__":
    main()
