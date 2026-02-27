"""
PUCK PREP — FastAPI Backend
Save-on-Foods Memorial Centre · F&B Intelligence Platform

Powered by damien's profile-matching forecast engine with partner's polished API interface.
"""

import os
import sys
import math
import json
import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional

# Add backend to sys.path so engine imports work
sys.path.insert(0, os.path.dirname(__file__))

from engine.data.profiles import build_profiles
from engine.data.enricher import enrich_games
from engine.data.loader import load_merged
from engine.models.forecast import generate_forecast, derive_archetype
from engine.models.correction import load_correction_model, get_correction_factor
from engine.models.prep_plan import generate_prep_plan
from engine.models.drift import DriftDetector
from engine.models.traffic_light import TrafficLightMonitor
from engine.simulator.engine import GameSimulator, NoiseConfig
from engine.simulator.scenarios import get_scenarios, list_scenarios
from engine.ai.reasoning import analyze_drift
from engine.ai.post_game import generate_post_game_report
from engine.ai.event_optimizer import analyze_promo_opportunities, generate_ai_event_recommendations
from engine.validation.backtest import run_backtest
from engine.config import STAND_SHORT, ITEM_PERISHABILITY, PREP_TARGET

from data_loader import (
    load_all_data,
    compute_item_stats,
    compute_dow_multipliers,
    compute_location_shares,
    compute_history_summary,
)

logger = logging.getLogger(__name__)


# ─── STATIC CONFIG ─────────────────────────────────────────────────────────────

ITEM_EMOJIS = {
    "Cans of Beer": "🍺", "Draught Beer": "🍺", "Draft Beer": "🍺",
    "Cider & Coolers": "🍹", "Bottle Pop": "🥤", "Water": "💧",
    "Other Beverages": "🧃", "Non-Alcoholic Beverages": "🧃",
    "Hot Drinks": "☕", "Popcorn": "🍿", "Pretzel": "🥨",
    "COMBOS": "🍘", "Chips": "🫙", "Hot Dog": "🌭",
    "Fries": "🍟", "Pizza Slice": "🍕", "Burgers": "🍔",
    "Candy": "🍬", "Gummies": "🍭", "Churro": "🥐",
    "Dogs": "🌭", "Tacos": "🌮", "Cotton Candy": "🍭",
    "Chicken Tenders": "🍗", "Sweet Potato Fries": "🍟",
    "Cookies & Brownies": "🍪", "Paletas": "🍦",
    "Wine by the Glass SOFMC": "🍷",
}

ITEM_CATEGORY_OVERRIDES = {
    "Cans of Beer": "Beer", "Draught Beer": "Beer", "Draft Beer": "Beer",
    "Cider & Coolers": "Alcohol",
    "Bottle Pop": "NA_Bev", "Water": "NA_Bev", "Other Beverages": "NA_Bev",
    "Non-Alcoholic Beverages": "NA_Bev", "Hot Drinks": "NA_Bev",
    "Popcorn": "Snack", "Pretzel": "Snack", "COMBOS": "Snack", "Chips": "Snack",
    "Hot Dog": "Food", "Fries": "Food", "Pizza Slice": "Food", "Burgers": "Food",
    "Candy": "Sweets", "Gummies": "Sweets", "Churro": "Sweets",
}

OUTCOME_MODIFIERS = {
    "win":     {"Beer": 1.18, "Alcohol": 1.15, "Food": 1.06, "Snack": 1.08, "NA_Bev": 1.05, "Sweets": 1.05},
    "loss":    {"Beer": 0.88, "Alcohol": 0.90, "Food": 0.97, "Snack": 0.95, "NA_Bev": 1.02, "Sweets": 0.97},
    "close":   {"Beer": 1.06, "Alcohol": 1.04, "Food": 1.02, "Snack": 1.02, "NA_Bev": 1.02, "Sweets": 1.02},
    "unknown": {"Beer": 1.00, "Alcohol": 1.00, "Food": 1.00, "Snack": 1.00, "NA_Bev": 1.00, "Sweets": 1.00},
}

GAME_TIMELINE = [
    {"label": "Pre-Game",       "offset_min": -60, "share": 0.18},
    {"label": "Period 1",       "offset_min":   0, "share": 0.26},
    {"label": "Intermission 1", "offset_min":  63, "share": 0.27},
    {"label": "Period 2",       "offset_min":  83, "share": 0.14},
    {"label": "Intermission 2", "offset_min": 146, "share": 0.11},
    {"label": "Period 3",       "offset_min": 166, "share": 0.04},
]

WHL_TEAMS = [
    "Brandon Wheat Kings", "Calgary Hitmen", "Edmonton Oil Kings",
    "Everett Silvertips", "Kamloops Blazers", "Kelowna Rockets",
    "Lethbridge Hurricanes", "Medicine Hat Tigers", "Moose Jaw Warriors",
    "Portland Winterhawks", "Prince Albert Raiders", "Prince George Cougars",
    "Red Deer Rebels", "Regina Pats", "Seattle Thunderbirds",
    "Spokane Chiefs", "Swift Current Broncos", "Tri-City Americans",
    "Vancouver Giants", "Wenatchee Wild",
]


# ─── DATA STATE ─────────────────────────────────────────────────────────────────

PROFILES = {}
GAMES = None
MERGED = None
CORRECTION_MODEL = None
ITEM_STATS = []
DOW_MULTIPLIERS = {}
LOCATION_SHARES = {}
LOCATION_TOP_ITEMS = {}
DATASET_META = {}
HISTORY_SUMMARY = {}
BACKTEST_CACHE = None
EVENT_RECS_CACHE = None
AI_STRATEGY_CACHE = None
HAS_AI = False


# ─── HELPERS ────────────────────────────────────────────────────────────────────

def infer_category(item_name: str) -> str:
    if item_name in ITEM_CATEGORY_OVERRIDES:
        return ITEM_CATEGORY_OVERRIDES[item_name]
    lower = item_name.lower()
    if "beer" in lower:
        return "Beer"
    if any(x in lower for x in ["cooler", "cider", "wine", "cocktail", "slushy", "boozy"]):
        return "Alcohol"
    if any(x in lower for x in ["water", "pop", "soda", "drink", "beverage", "juice", "coffee"]):
        return "NA_Bev"
    if any(x in lower for x in ["candy", "gummi", "chocolate", "churro", "cookie", "brownie", "paleta"]):
        return "Sweets"
    if any(x in lower for x in ["dog", "burger", "pizza", "fries", "nacho", "taco", "chicken", "panini"]):
        return "Food"
    return "Snack"


def home_support_modifier(pct: int) -> float:
    return round(1.0 + ((pct - 50) / 40.0) * 0.10, 4)


def confidence_interval(mean: float, std: float, predicted: float) -> tuple[int, int]:
    band = (std / mean) * 0.5 if mean > 0 else 0.3
    return (
        max(0, math.floor(predicted * (1 - band))),
        math.ceil(predicted * (1 + band)),
    )


def build_timeline(puck_drop: str, total_items: int) -> list[dict]:
    from datetime import datetime as _dt
    for fmt in ("%I:%M %p", "%H:%M"):
        try:
            t = _dt.strptime(puck_drop.strip(), fmt)
            h, m = t.hour, t.minute
            break
        except ValueError:
            continue
    else:
        h, m = 19, 0  # default 7 PM
    puck_min = h * 60 + m
    result = []
    for slot in GAME_TIMELINE:
        abs_min = puck_min + slot["offset_min"]
        hh, mm = divmod(abs_min % (24 * 60), 60)
        result.append({
            "label": slot["label"],
            "clock_time": f"{hh:02d}:{mm:02d}",
            "items": round(total_items * slot["share"]),
            "share_pct": round(slot["share"] * 100),
            "is_rush": slot["label"].startswith("Intermission"),
        })
    return result


# ─── STARTUP ────────────────────────────────────────────────────────────────────

def load_model_data() -> None:
    global PROFILES, GAMES, MERGED, CORRECTION_MODEL
    global ITEM_STATS, DOW_MULTIPLIERS, LOCATION_SHARES, LOCATION_TOP_ITEMS
    global DATASET_META, HISTORY_SUMMARY
    global BACKTEST_CACHE, EVENT_RECS_CACHE, AI_STRATEGY_CACHE, HAS_AI

    print("\n━━━ Puck Prep: Loading engine ━━━")

    # Check for AI capability
    HAS_AI = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if HAS_AI:
        print("  AI: Anthropic API key found ✓")
    else:
        print("  AI: No API key — using rule-based fallbacks")

    try:
        # ── Load damien's engine ──────────────────────────────────────
        print("  Building profiles...")
        PROFILES = build_profiles()
        GAMES = enrich_games()
        MERGED = load_merged()
        CORRECTION_MODEL = load_correction_model()

        if CORRECTION_MODEL:
            print(f"  Correction model: {CORRECTION_MODEL['method']} (n={CORRECTION_MODEL['n_games']})")

        # ── Load partner's item stats (for confidence/variance) ───────
        print("  Computing item stats...")
        import pandas as pd
        sales, games_raw = load_all_data()
        stats = compute_item_stats(sales, games_raw)
        dow = compute_dow_multipliers(sales, games_raw)
        shares, top_items = compute_location_shares(sales, games_raw)
        history = compute_history_summary(sales, games_raw)

        std_filled = stats["std_per100"].fillna(stats["mean_per100"] * 0.3)
        mapped_items = []
        for row, std_val in zip(stats.to_dict(orient="records"), std_filled):
            item_name = row["Item"]
            mean_v = float(row["mean_per100"])
            std_v = float(std_val)
            variance_pct = round((std_v / mean_v) * 100, 1) if mean_v else 0.0
            mapped_items.append({
                "item": item_name,
                "emoji": ITEM_EMOJIS.get(item_name, "🍽️"),
                "category": infer_category(item_name),
                "mean_per100": round(mean_v, 4),
                "std_per100": round(std_v, 4),
                "confidence": row["confidence"],
                "variance_pct": variance_pct,
                "games_count": int(row["games_count"]),
                "total_qty": int(row["total_qty"]),
            })

        ITEM_STATS = mapped_items
        DOW_MULTIPLIERS = {str(k): float(v) for k, v in dow.items()}
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            DOW_MULTIPLIERS.setdefault(day, 1.0)
        LOCATION_SHARES = {str(k): float(v) for k, v in shares.items()}
        LOCATION_TOP_ITEMS = {str(k): [str(x) for x in v] for k, v in top_items.items()}

        merged_check = sales.merge(
            games_raw[["GameDate", "Attendance"]], left_on="Date", right_on="GameDate", how="inner"
        )
        per_game_totals = merged_check.groupby(["GameDate", "Attendance"])["Qty"].sum().reset_index()
        corr = per_game_totals[["Attendance", "Qty"]].corr().iloc[0, 1]
        r2 = round(float(corr ** 2), 4)

        DATASET_META = {
            "games_in_dataset": int(history["total_games"]),
            "transactions": int(history["total_transactions"]),
            "r_squared": r2,
        }

        HISTORY_SUMMARY = {
            **history,
            "seasons": ["2024/25", "2025/26"],
            "r_squared": r2,
            "top_items": [
                {"item": r["Item"], "total_qty": int(r["total_qty"]), "rank": idx + 1}
                for idx, r in enumerate(
                    stats.sort_values("total_qty", ascending=False)
                    .head(5).to_dict(orient="records")
                )
            ],
            "dow_multipliers": DOW_MULTIPLIERS,
            "location_shares": LOCATION_SHARES,
        }

        # ── Pre-compute expensive operations ──────────────────────────
        print("  Pre-computing backtest (cached)...")
        try:
            BACKTEST_CACHE = [r.to_dict() for r in run_backtest()]
            within_15 = sum(1 for r in BACKTEST_CACHE if abs(r["volume_error"]) <= 0.15)
            print(f"  Backtest: {within_15}/{len(BACKTEST_CACHE)} games within ±15%")
        except Exception as e:
            print(f"  Backtest pre-compute failed: {e}")
            BACKTEST_CACHE = []

        print("  Pre-computing event recommendations...")
        try:
            recs = analyze_promo_opportunities()
            EVENT_RECS_CACHE = [r.to_dict() for r in recs]
            if HAS_AI:
                AI_STRATEGY_CACHE = generate_ai_event_recommendations(recs)
            else:
                AI_STRATEGY_CACHE = None
        except Exception as e:
            print(f"  Event recommendations failed: {e}")
            EVENT_RECS_CACHE = []
            AI_STRATEGY_CACHE = None

        n_games = len(GAMES) if GAMES is not None else 0
        n_items = len(ITEM_STATS)
        print(f"  Items tracked : {n_items}")
        print(f"  Games loaded  : {n_games}")
        print(f"  Transactions  : {DATASET_META.get('transactions', 0):,}")
        print(f"  R²            : {r2}")
        print("━━━ Engine ready ━━━\n")

    except Exception as exc:
        logger.error("Failed to load data: %s", exc, exc_info=True)
        raise RuntimeError(f"Cannot start — data files missing or unreadable: {exc}")


# ─── LIFESPAN ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model_data()
    yield

app = FastAPI(title="Puck Prep API", version="3.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── SCHEMAS ────────────────────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    opponent: str = Field(..., description="WHL opponent team name")
    day_of_week: str = Field(..., description="e.g. Friday")
    puck_drop: str = Field(..., description="e.g. 19:05")
    attendance: int = Field(..., ge=500, le=8000)
    predicted_outcome: Literal["win", "loss", "close", "unknown"] = "unknown"
    home_support_pct: int = Field(70, ge=10, le=95)
    game_date: Optional[str] = None


# ─── ROUTES ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Puck Prep API",
        "version": "3.0.0",
        "status": "live",
        "engine": "profile-matching forecast",
        "ai_available": HAS_AI,
        "games_in_dataset": DATASET_META.get("games_in_dataset"),
        "transactions": DATASET_META.get("transactions"),
        "r_squared": DATASET_META.get("r_squared"),
    }


@app.get("/teams")
def get_teams():
    return {"teams": WHL_TEAMS}


@app.post("/forecast")
def forecast(req: ForecastRequest):
    """Generate forecast using damien's engine, wrapped in partner's response shape."""

    # ── Damien's engine: generate the real forecast ───────────────────
    puck_drop_hour = int(req.puck_drop.split(":")[0]) if ":" in req.puck_drop else 19
    day_short = req.day_of_week[:3]

    engine_forecast = generate_forecast(
        attendance=req.attendance,
        puck_drop_hour=puck_drop_hour,
        is_playoff=False,
        is_promo=False,
        promo_type="",
        temp_mean=8.0,  # default; could be enriched from weather API
        day_of_week=day_short,
        profiles=PROFILES,
    )

    archetype = engine_forecast["archetype"]
    scale_factor = engine_forecast["scale_factor"]
    beer_factor = engine_forecast["beer_factor"]

    # ── Apply correction model if available ───────────────────────────
    correction_factor = 1.0
    if CORRECTION_MODEL is not None:
        import pandas as pd
        game_features = pd.Series({
            "attendance": req.attendance,
            "is_weekend": req.day_of_week in ("Friday", "Saturday", "Sunday"),
            "is_promo": False,
            "is_playoff": False,
            "temp_mean": 8.0,
            "archetype": archetype,
            "opponent_division": "Unknown",
            "puck_drop_hour": puck_drop_hour,
        })
        correction_factor = get_correction_factor(game_features, CORRECTION_MODEL)

    item_fc = engine_forecast["item_forecast"]
    if correction_factor != 1.0:
        item_fc["expected_qty"] = (item_fc["expected_qty"] * correction_factor).round(0).astype(int)
        item_fc["prep_qty"] = (item_fc["prep_qty"] * correction_factor).round(0).astype(int)

    # ── Partner's modifiers: outcome + home support ───────────────────
    dow_mult = DOW_MULTIPLIERS.get(req.day_of_week, 1.0)
    home_mod = home_support_modifier(req.home_support_pct)
    outcome_mod = OUTCOME_MODIFIERS.get(req.predicted_outcome, OUTCOME_MODIFIERS["unknown"])

    # ── Build per-item response (merge engine forecast with item stats) ──
    # Collapse time windows → per-item totals from engine
    engine_items = item_fc.groupby("item").agg(
        engine_predicted=("expected_qty", "sum"),
        engine_prep=("prep_qty", "sum"),
    ).reset_index()

    # Build item_stats lookup
    stats_lookup = {s["item"]: s for s in ITEM_STATS}

    all_items = []
    for _, row in engine_items.iterrows():
        item_name = row["item"]
        base_predicted = int(row["engine_predicted"])
        prep_qty = int(row["engine_prep"])

        # Apply outcome + home support mods on top of engine forecast
        cat = infer_category(item_name)
        out_mod = outcome_mod.get(cat, 1.0)
        predicted = round(base_predicted * out_mod * home_mod)
        prep_qty = round(prep_qty * out_mod * home_mod)

        # Get confidence/variance from partner's stats
        stat = stats_lookup.get(item_name, {})
        mean_v = stat.get("mean_per100", 0)
        std_v = stat.get("std_per100", mean_v * 0.3)
        variance_pct = stat.get("variance_pct", 30.0)
        conf = stat.get("confidence", "medium")

        low, high = confidence_interval(max(mean_v, 0.01), max(std_v, 0.01), predicted)

        perishability = ITEM_PERISHABILITY.get(item_name, "medium_hold")

        all_items.append({
            "item": item_name,
            "emoji": ITEM_EMOJIS.get(item_name, "🍽️"),
            "category": cat,
            "confidence": conf,
            "variance_pct": variance_pct,
            "predicted": predicted,
            "prep_qty": prep_qty,
            "low": low,
            "high": high,
            "base_qty": base_predicted,
            "perishability": perishability,
        })

    # Sort by predicted desc
    all_items.sort(key=lambda x: -x["predicted"])
    total_predicted = sum(i["predicted"] for i in all_items)

    # ── Per-stand breakdown from engine's stand_item_forecast ─────────
    stands = []
    si_forecast = engine_forecast.get("stand_item_forecast")
    if si_forecast is not None and not si_forecast.empty:
        for stand_name, group in si_forecast.groupby("stand"):
            short_name = STAND_SHORT.get(stand_name, stand_name.replace("SOFMC ", ""))
            stand_total = int(group["expected_qty"].sum())
            share = stand_total / total_predicted if total_predicted > 0 else 0

            stand_items = []
            for _, si_row in group.groupby("item").agg(
                predicted=("expected_qty", "sum"),
                prep_qty=("prep_qty", "sum"),
            ).reset_index().sort_values("predicted", ascending=False).head(7).iterrows():
                item_name = si_row["item"]
                cat = infer_category(item_name)
                pred = round(int(si_row["predicted"]) * out_mod * home_mod)
                stat = stats_lookup.get(item_name, {})
                mean_v = stat.get("mean_per100", 0.01)
                std_v = stat.get("std_per100", mean_v * 0.3)
                low, high = confidence_interval(max(mean_v, 0.01), max(std_v, 0.01), pred)
                stand_items.append({
                    "item": item_name,
                    "emoji": ITEM_EMOJIS.get(item_name, "🍽️"),
                    "category": cat,
                    "confidence": stat.get("confidence", "medium"),
                    "predicted": pred,
                    "low": low,
                    "high": high,
                })

            stands.append({
                "name": short_name,
                "volume_share_pct": round(share * 100, 1),
                "total_predicted": round(stand_total * out_mod * home_mod),
                "items": stand_items,
            })
        stands.sort(key=lambda x: -x["total_predicted"])
    else:
        # Fallback: use partner's location shares
        for stand_name, share in LOCATION_SHARES.items():
            top_names = LOCATION_TOP_ITEMS.get(stand_name, [])
            stand_items = []
            for item in all_items:
                if item["item"] not in top_names:
                    continue
                f = share * 1.6
                stand_items.append({
                    "item": item["item"],
                    "emoji": item["emoji"],
                    "category": item["category"],
                    "confidence": item["confidence"],
                    "predicted": round(item["predicted"] * f),
                    "low": round(item["low"] * f),
                    "high": round(item["high"] * f),
                })
            stand_items.sort(key=lambda x: -x["predicted"])
            stands.append({
                "name": stand_name,
                "volume_share_pct": round(share * 100, 1),
                "total_predicted": sum(i["predicted"] for i in stand_items),
                "items": stand_items,
            })
        stands.sort(key=lambda x: -x["total_predicted"])

    # ── Timeline + watchlist ──────────────────────────────────────────
    timeline = build_timeline(req.puck_drop, total_predicted)
    watchlist = [i for i in all_items if i["confidence"] == "low" or i["variance_pct"] > 40]

    # ── Prep targets summary ─────────────────────────────────────────
    total_prep = sum(i["prep_qty"] for i in all_items)
    prep_targets = {
        "total_prep_qty": total_prep,
        "prep_pct_of_forecast": round(total_prep / total_predicted * 100, 1) if total_predicted > 0 else 0,
        "tiers": {
            "shelf_stable": {"target_pct": 95, "items": sum(1 for i in all_items if i["perishability"] == "shelf_stable")},
            "medium_hold": {"target_pct": 85, "items": sum(1 for i in all_items if i["perishability"] == "medium_hold")},
            "short_life": {"target_pct": 75, "items": sum(1 for i in all_items if i["perishability"] == "short_life")},
        }
    }

    return {
        "meta": {
            "opponent": req.opponent,
            "day_of_week": req.day_of_week,
            "puck_drop": req.puck_drop,
            "attendance": req.attendance,
            "predicted_outcome": req.predicted_outcome,
            "home_support_pct": req.home_support_pct,
            "game_date": req.game_date,
            "archetype": archetype,
        },
        "summary": {
            "total_predicted": total_predicted,
            "total_low": sum(i["low"] for i in all_items),
            "total_high": sum(i["high"] for i in all_items),
            "items_per_fan": round(total_predicted / req.attendance, 2),
            "r_squared": DATASET_META.get("r_squared", 0.9),
            "games_in_model": DATASET_META.get("games_in_dataset", 0),
        },
        "modifiers": {
            "day_of_week": {"label": req.day_of_week, "multiplier": round(dow_mult, 3)},
            "home_support": {"label": f"{req.home_support_pct}% Royals fans", "multiplier": round(home_mod, 3)},
            "predicted_outcome": {"label": req.predicted_outcome, "modifiers": outcome_mod},
        },
        "engine": {
            "archetype": archetype,
            "scale_factor": scale_factor,
            "correction_factor": round(correction_factor, 3),
            "beer_factor": beer_factor,
        },
        "ai_brief": None,
        "items": all_items,
        "stands": stands,
        "timeline": timeline,
        "watchlist": watchlist,
        "prep_targets": prep_targets,
    }


@app.get("/history/summary")
def history_summary():
    return HISTORY_SUMMARY


# ─── SIMULATION ENDPOINTS ───────────────────────────────────────────────────────

@app.get("/scenarios")
def get_scenario_list():
    """List available simulation scenarios."""
    try:
        return {"scenarios": list_scenarios()}
    except Exception as e:
        return {"scenarios": [], "error": str(e)}


@app.websocket("/ws/simulation")
async def simulation_websocket(websocket: WebSocket):
    """Real-time game simulation via WebSocket."""
    await websocket.accept()

    try:
        # Receive configuration
        config = await websocket.receive_json()
        scenario_key = config.get("scenario", "normal")
        speed = config.get("speed", 60)
        skip_ai = config.get("skip_ai", not HAS_AI)

        scenarios = get_scenarios()
        if scenario_key not in scenarios:
            await websocket.send_json({"type": "error", "message": f"Unknown scenario: {scenario_key}"})
            return

        scenario = scenarios[scenario_key]

        await websocket.send_json({
            "type": "init",
            "scenario": {"key": scenario_key, "name": scenario.name, "description": scenario.description},
        })

        # Build simulator and forecast
        sim = scenario.build_simulator(speed=speed)
        game_info = sim.game_info

        forecast = generate_forecast(
            attendance=game_info["attendance"],
            puck_drop_hour=int(sim.game_meta.get("puck_drop_hour", 19)),
            is_playoff=bool(sim.game_meta.get("is_playoff", False)),
            is_promo=bool(sim.game_meta.get("is_promo", False)),
            promo_type=str(sim.game_meta.get("promo_type", "")),
            temp_mean=float(sim.game_meta.get("temp_mean", 8.0)),
            day_of_week=str(sim.game_meta.get("day_of_week", "Fri")),
            profiles=PROFILES,
        )

        await websocket.send_json({
            "type": "game_info",
            "game": game_info,
            "archetype": forecast["archetype"],
            "scale_factor": forecast["scale_factor"],
        })

        # Setup drift detection
        detector = DriftDetector(forecast)
        monitor = TrafficLightMonitor(detector)
        reasoning_results = []

        # Run simulation in background thread
        loop = asyncio.get_event_loop()
        current_window = [None]
        window_count = [0]

        def on_event(event):
            detector.ingest_event(event)

        def on_window(tw, events):
            current_window[0] = tw
            window_count[0] += 1

            # Check drift
            drift_report = detector.check_drift(tw)
            status = monitor.update(tw)

            # Send update via WebSocket
            msg = {
                "type": "window_update",
                "time_window": tw,
                "window_number": window_count[0],
                "drift": drift_report.to_dict(),
                "traffic_light": status.to_dict(),
                "events_in_window": len(events),
                "cumulative_drift": round(detector.cumulative_drift(), 3),
            }

            # AI reasoning for significant drift
            if drift_report.has_significant_drift and not skip_ai:
                try:
                    reasoning = analyze_drift(
                        drift_report, game_info,
                        cumulative_drift=detector.cumulative_drift(),
                        recent_reports=detector.history[-4:-1],
                    )
                    reasoning_results.append(reasoning)
                    msg["ai_alert"] = reasoning.to_dict()
                except Exception:
                    pass
            elif drift_report.has_significant_drift:
                # Rule-based fallback
                from engine.ai.reasoning import _fallback_classify
                reasoning = _fallback_classify(drift_report, detector.cumulative_drift(), "AI disabled")
                reasoning_results.append(reasoning)
                msg["ai_alert"] = reasoning.to_dict()

            asyncio.run_coroutine_threadsafe(
                websocket.send_json(msg), loop
            )

        sim.observers = [on_event]
        sim.window_observers = [on_window]

        # Run in thread
        def run_sim():
            sim.run(realtime=True)

        thread = threading.Thread(target=run_sim, daemon=True)
        thread.start()

        # Wait for completion
        while thread.is_alive():
            try:
                # Check for client messages (speed changes, stop)
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
                if msg.get("action") == "stop":
                    break
                if msg.get("action") == "speed":
                    sim.speed = msg.get("value", sim.speed)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                return

        thread.join(timeout=5)

        # Post-game report
        summary = detector.summary()
        post_game = None
        if not skip_ai:
            try:
                post_game = generate_post_game_report(
                    game_info, detector, reasoning_results, forecast
                )
            except Exception:
                pass

        await websocket.send_json({
            "type": "complete",
            "summary": summary,
            "post_game_report": post_game,
            "total_ai_alerts": len(reasoning_results),
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ─── VALIDATION ENDPOINT ────────────────────────────────────────────────────────

@app.get("/validation/backtest")
def get_backtest():
    """Return pre-computed LOO backtest results."""
    if BACKTEST_CACHE is None:
        return {"results": [], "error": "Backtest not computed"}

    results = BACKTEST_CACHE
    n = len(results)
    if n == 0:
        return {"results": [], "summary": {}}

    errors = [abs(r["volume_error"]) for r in results]
    within_15 = sum(1 for e in errors if e <= 0.15)
    within_25 = sum(1 for e in errors if e <= 0.25)

    # Archetype breakdown
    archetype_stats = {}
    for r in results:
        arch = r["archetype"]
        if arch not in archetype_stats:
            archetype_stats[arch] = {"count": 0, "errors": [], "games": []}
        archetype_stats[arch]["count"] += 1
        archetype_stats[arch]["errors"].append(r["volume_error"])
        archetype_stats[arch]["games"].append(r)

    arch_summary = {}
    for arch, data in archetype_stats.items():
        errs = data["errors"]
        import statistics
        arch_summary[arch] = {
            "count": data["count"],
            "median_error": round(statistics.median(errs), 4),
            "mean_abs_error": round(sum(abs(e) for e in errs) / len(errs), 4),
            "within_15pct": sum(1 for e in errs if abs(e) <= 0.15),
        }

    return {
        "results": results,
        "summary": {
            "total_games": n,
            "median_error": round(statistics.median([r["volume_error"] for r in results]), 4),
            "mean_abs_error": round(sum(errors) / n, 4),
            "within_15pct": within_15,
            "within_15pct_rate": round(within_15 / n, 3),
            "within_25pct": within_25,
            "within_25pct_rate": round(within_25 / n, 3),
            "total_waste_units": sum(r["waste_units"] for r in results),
            "total_stockout_units": sum(r["stockout_units"] for r in results),
        },
        "archetype_breakdown": arch_summary,
    }


# ─── AI / EVENT ENDPOINTS ──────────────────────────────────────────────────────

@app.get("/ai/event-recommendations")
def get_event_recommendations():
    """Return promo/event optimization recommendations."""
    return {
        "recommendations": EVENT_RECS_CACHE or [],
        "ai_strategy": AI_STRATEGY_CACHE,
        "ai_available": HAS_AI,
    }
