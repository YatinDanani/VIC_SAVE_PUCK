"""
PUCK PREP — FastAPI Backend
Save-on-Foods Memorial Centre · F&B Intelligence Platform

Data is loaded entirely from /data files via data_loader.py at startup.
No hardcoded model constants — drop new files in /data and restart to update.
"""

import os
import math
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional

from data_loader import (
    load_all_data,
    compute_item_stats,
    compute_dow_multipliers,
    compute_location_shares,
    compute_history_summary,
)

app = FastAPI(title="Puck Prep API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)


# ─── STATIC CONFIG (never changes, not data) ──────────────────────────────────

ITEM_EMOJIS = {
    "Cans of Beer":   "🍺", "Draught Beer":  "🍺", "Draft Beer":    "🍺",
    "Cider & Coolers":"🍹", "Bottle Pop":    "🥤", "Water":         "💧",
    "Other Beverages":"🧃", "Non-Alcoholic Beverages":"🧃",
    "Hot Drinks":     "☕", "Popcorn":       "🍿", "Pretzel":       "🥨",
    "COMBOS":         "🍘", "Chips":         "🫙", "Hot Dog":       "🌭",
    "Fries":          "🍟", "Pizza Slice":   "🍕", "Burgers":       "🍔",
    "Candy":          "🍬", "Gummies":       "🍭", "Churro":        "🥐",
}

ITEM_CATEGORY_OVERRIDES = {
    "Cans of Beer": "Beer",   "Draught Beer": "Beer",    "Draft Beer":   "Beer",
    "Cider & Coolers": "Alcohol",
    "Bottle Pop": "NA_Bev",   "Water": "NA_Bev",         "Other Beverages": "NA_Bev",
    "Non-Alcoholic Beverages": "NA_Bev",                 "Hot Drinks": "NA_Bev",
    "Popcorn": "Snack",       "Pretzel": "Snack",        "COMBOS": "Snack",
    "Chips": "Snack",
    "Hot Dog": "Food",        "Fries": "Food",            "Pizza Slice": "Food",
    "Burgers": "Food",
    "Candy": "Sweets",        "Gummies": "Sweets",        "Churro": "Sweets",
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


# ─── DATA STATE (populated at startup from real files) ────────────────────────

ITEM_STATS         = []
DOW_MULTIPLIERS    = {}
LOCATION_SHARES    = {}
LOCATION_TOP_ITEMS = {}
DATASET_META       = {}
HISTORY_SUMMARY    = {}


# ─── HELPERS ──────────────────────────────────────────────────────────────────

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
    """50% neutral → 1.0  |  90% home → +10%  |  20% home → -8%"""
    return round(1.0 + ((pct - 50) / 40.0) * 0.10, 4)


def confidence_interval(mean: float, std: float, predicted: float) -> tuple[int, int]:
    band = (std / mean) * 0.5
    return (
        max(0, math.floor(predicted * (1 - band))),
        math.ceil(predicted * (1 + band)),
    )


def build_timeline(puck_drop: str, total_items: int) -> list[dict]:
    h, m     = map(int, puck_drop.split(":"))
    puck_min = h * 60 + m
    result   = []
    for slot in GAME_TIMELINE:
        abs_min  = puck_min + slot["offset_min"]
        hh, mm   = divmod(abs_min % (24 * 60), 60)
        result.append({
            "label":      slot["label"],
            "clock_time": f"{hh:02d}:{mm:02d}",
            "items":      round(total_items * slot["share"]),
            "share_pct":  round(slot["share"] * 100),
            "is_rush":    slot["label"].startswith("Intermission"),
        })
    return result


# ─── STARTUP ──────────────────────────────────────────────────────────────────

def load_model_data() -> None:
    global ITEM_STATS, DOW_MULTIPLIERS, LOCATION_SHARES, LOCATION_TOP_ITEMS
    global DATASET_META, HISTORY_SUMMARY

    print("\n━━━ Puck Prep: Loading data files ━━━")
    try:
        import pandas as pd

        sales, games             = load_all_data()
        stats                    = compute_item_stats(sales, games)
        dow                      = compute_dow_multipliers(sales, games)
        shares, top_items        = compute_location_shares(sales, games)
        history                  = compute_history_summary(sales, games)

        std_filled = stats["std_per100"].fillna(stats["mean_per100"] * 0.3)
        mapped_items = []
        for row, std_val in zip(stats.to_dict(orient="records"), std_filled):
            item_name    = row["Item"]
            mean_v       = float(row["mean_per100"])
            std_v        = float(std_val)
            variance_pct = round((std_v / mean_v) * 100, 1) if mean_v else 0.0
            mapped_items.append({
                "item":         item_name,
                "emoji":        ITEM_EMOJIS.get(item_name, "🍽️"),
                "category":     infer_category(item_name),
                "mean_per100":  round(mean_v, 4),
                "std_per100":   round(std_v, 4),
                "confidence":   row["confidence"],
                "variance_pct": variance_pct,
                "games_count":  int(row["games_count"]),
                "total_qty":    int(row["total_qty"]),
            })

        ITEM_STATS         = mapped_items
        DOW_MULTIPLIERS    = {str(k): float(v) for k, v in dow.items()}
        for day in ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]:
            DOW_MULTIPLIERS.setdefault(day, 1.0)
        LOCATION_SHARES    = {str(k): float(v) for k, v in shares.items()}
        LOCATION_TOP_ITEMS = {str(k): [str(x) for x in v] for k, v in top_items.items()}

        merged_check    = sales.merge(
            games[["GameDate", "Attendance"]], left_on="Date", right_on="GameDate", how="inner"
        )
        per_game_totals = merged_check.groupby(["GameDate","Attendance"])["Qty"].sum().reset_index()
        corr            = per_game_totals[["Attendance","Qty"]].corr().iloc[0,1]
        r2              = round(float(corr ** 2), 4)

        DATASET_META = {
            "games_in_dataset": int(history["total_games"]),
            "transactions":     int(history["total_transactions"]),
            "r_squared":        r2,
        }

        HISTORY_SUMMARY = {
            **history,
            "seasons":       ["2024/25", "2025/26"],
            "r_squared":     r2,
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

        print(f"  Items tracked : {len(ITEM_STATS)}")
        print(f"  Games loaded  : {DATASET_META['games_in_dataset']}")
        print(f"  Transactions  : {DATASET_META['transactions']:,}")
        print(f"  R²            : {r2}")
        print("━━━ Data ready ━━━\n")

    except Exception as exc:
        logger.error("Failed to load data files: %s", exc)
        raise RuntimeError(
            f"Cannot start — data files missing or unreadable: {exc}\n"
            "Place GameDetails.xlsx and items-*.csv in backend/data/"
        )


load_model_data()


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    opponent:          str                                     = Field(..., description="WHL opponent team name")
    day_of_week:       str                                     = Field(..., description="e.g. Friday")
    puck_drop:         str                                     = Field(..., description="e.g. 19:05")
    attendance:        int                                     = Field(..., ge=500, le=8000)
    predicted_outcome: Literal["win","loss","close","unknown"] = "unknown"
    home_support_pct:  int                                     = Field(70, ge=10, le=95)
    game_date:         Optional[str]                           = None


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service":           "Puck Prep API",
        "status":            "live",
        "games_in_dataset":  DATASET_META.get("games_in_dataset"),
        "transactions":      DATASET_META.get("transactions"),
        "r_squared":         DATASET_META.get("r_squared"),
    }


@app.get("/teams")
def get_teams():
    return {"teams": WHL_TEAMS}


@app.post("/forecast")
def forecast(req: ForecastRequest):
    dow_mult    = DOW_MULTIPLIERS.get(req.day_of_week, 1.0)
    home_mod    = home_support_modifier(req.home_support_pct)
    outcome_mod = OUTCOME_MODIFIERS.get(req.predicted_outcome, OUTCOME_MODIFIERS["unknown"])

    # ── Per-item predictions ──
    all_items = []
    for stat in ITEM_STATS:
        cat         = stat["category"]
        base        = (stat["mean_per100"] / 100.0) * req.attendance
        predicted_f = base * dow_mult * outcome_mod.get(cat, 1.0) * home_mod
        predicted   = round(predicted_f)
        low, high   = confidence_interval(stat["mean_per100"], stat["std_per100"], predicted_f)
        all_items.append({
            "item":         stat["item"],
            "emoji":        stat["emoji"],
            "category":     cat,
            "confidence":   stat["confidence"],
            "variance_pct": stat["variance_pct"],
            "predicted":    predicted,
            "low":          low,
            "high":         high,
            "base_qty":     round(base),
            "dow_adj":      round(base * dow_mult),
        })

    total_predicted = sum(i["predicted"] for i in all_items)

    # ── Per-stand breakdown ──
    stands = []
    for stand_name, share in LOCATION_SHARES.items():
        top_names   = LOCATION_TOP_ITEMS.get(stand_name, [])
        stand_items = []
        for item in all_items:
            if item["item"] not in top_names:
                continue
            f = share * 1.6
            stand_items.append({
                "item":       item["item"],
                "emoji":      item["emoji"],
                "category":   item["category"],
                "confidence": item["confidence"],
                "predicted":  round(item["predicted"] * f),
                "low":        round(item["low"]        * f),
                "high":       round(item["high"]       * f),
            })
        stand_items.sort(key=lambda x: -x["predicted"])
        stands.append({
            "name":             stand_name,
            "volume_share_pct": round(share * 100, 1),
            "total_predicted":  sum(i["predicted"] for i in stand_items),
            "items":            stand_items,
        })
    stands.sort(key=lambda x: -x["total_predicted"])

    # ── Timeline + watchlist ──
    timeline  = build_timeline(req.puck_drop, total_predicted)
    watchlist = [i for i in all_items if i["confidence"] == "low" or i["variance_pct"] > 40]

    return {
        "meta": {
            "opponent":          req.opponent,
            "day_of_week":       req.day_of_week,
            "puck_drop":         req.puck_drop,
            "attendance":        req.attendance,
            "predicted_outcome": req.predicted_outcome,
            "home_support_pct":  req.home_support_pct,
            "game_date":         req.game_date,
        },
        "summary": {
            "total_predicted": total_predicted,
            "total_low":       sum(i["low"]  for i in all_items),
            "total_high":      sum(i["high"] for i in all_items),
            "items_per_fan":   round(total_predicted / req.attendance, 2),
            "r_squared":       DATASET_META.get("r_squared", 0.9),
            "games_in_model":  DATASET_META.get("games_in_dataset", 0),
        },
        "modifiers": {
            "day_of_week":       {"label": req.day_of_week,                        "multiplier": round(dow_mult, 3)},
            "home_support":      {"label": f"{req.home_support_pct}% Royals fans", "multiplier": round(home_mod, 3)},
            "predicted_outcome": {"label": req.predicted_outcome,                  "modifiers":  outcome_mod},
        },
        "ai_brief":  None,
        "items":     all_items,
        "stands":    stands,
        "timeline":  timeline,
        "watchlist": watchlist,
    }


@app.get("/history/summary")
def history_summary():
    return HISTORY_SUMMARY