# backend/data_loader.py

import pandas as pd
import glob
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def load_all_data():
    # Load all CSVs
    csv_files = sorted(glob.glob(os.path.join(DATA_DIR, "items-*.csv")))
    dfs = [pd.read_csv(f) for f in csv_files]
    sales = pd.concat(dfs, ignore_index=True)
    sales["Date"] = pd.to_datetime(sales["Date"])
    sales["Time"] = pd.to_datetime(sales["Time"], format="%H:%M:%S", errors="coerce")
    sales["Hour"] = sales["Time"].dt.hour

    # Load games
    games = pd.read_excel(os.path.join(DATA_DIR, "GameDetails.xlsx"))
    games = games[
        games["Attendance - Scanned"].notna() & 
        (games["Event"] != "Event")
    ].copy()
    games["GameDate"] = pd.to_datetime(games[games.columns[3]])
    games["Attendance"] = pd.to_numeric(games["Attendance - Scanned"])
    games["DayOfWeek"] = games["GameDate"].dt.day_name()

    return sales, games


def compute_item_stats(sales, games):
    """Compute per-item mean and std per 100 fans across all games."""
    merged = sales.merge(
        games[["GameDate", "Attendance"]],
        left_on="Date", right_on="GameDate", how="inner"
    )
    per_game = merged.groupby(["GameDate", "Attendance", "Item"])["Qty"].sum().reset_index()
    per_game["per100"] = per_game["Qty"] / per_game["Attendance"] * 100

    stats = per_game.groupby("Item").agg(
        games_count=("GameDate", "count"),
        mean_per100=("per100", "mean"),
        std_per100=("per100", "std"),
        total_qty=("Qty", "sum"),
    ).reset_index()

    # Only trust items with 10+ games of data
    stats = stats[stats["games_count"] >= 10].sort_values("total_qty", ascending=False)

    def confidence(row):
        ratio = row["std_per100"] / row["mean_per100"]
        if ratio < 0.20: return "high"
        if ratio < 0.45: return "medium"
        return "low"

    stats["confidence"] = stats.apply(confidence, axis=1)
    return stats


def compute_dow_multipliers(sales, games):
    """Day-of-week multipliers normalized to overall average."""
    merged = sales.merge(
        games[["GameDate", "Attendance", "DayOfWeek"]],
        left_on="Date", right_on="GameDate", how="inner"
    )
    per_game = merged.groupby(["GameDate", "DayOfWeek", "Attendance"])["Qty"].sum().reset_index()
    per_game["per_fan"] = per_game["Qty"] / per_game["Attendance"]
    overall_mean = per_game["per_fan"].mean()
    dow = per_game.groupby("DayOfWeek")["per_fan"].mean()
    return (dow / overall_mean).to_dict()


def compute_location_shares(sales, games):
    """Volume share per stand and top items per stand."""
    merged = sales.merge(
        games[["GameDate"]], left_on="Date", right_on="GameDate", how="inner"
    )
    merged["Location"] = merged["Location"].str.replace("SOFMC ", "")

    loc_totals = merged.groupby("Location")["Qty"].sum()
    shares = (loc_totals / loc_totals.sum()).to_dict()

    loc_item = merged.groupby(["Location", "Item"])["Qty"].sum().reset_index()
    top_items = {}
    for loc, grp in loc_item.groupby("Location"):
        top = grp.sort_values("Qty", ascending=False).head(7)["Item"].tolist()
        top_items[loc] = top

    return shares, top_items


def compute_history_summary(sales, games):
    merged = sales.merge(
        games[["GameDate", "Attendance", "Event"]],
        left_on="Date", right_on="GameDate", how="inner"
    )
    per_game = merged.groupby(["GameDate", "Attendance"])["Qty"].sum().reset_index()

    best = per_game.loc[per_game["Qty"].idxmax()]
    worst = per_game.loc[per_game["Qty"].idxmin()]

    return {
        "total_transactions": len(sales),
        "total_games": len(per_game),
        "attendance_range": {
            "min": int(per_game["Attendance"].min()),
            "max": int(per_game["Attendance"].max()),
            "avg": int(per_game["Attendance"].mean()),
        },
        "best_game": {
            "date": str(best["GameDate"])[:10],
            "attendance": int(best["Attendance"]),
            "items_sold": int(best["Qty"]),
        },
        "worst_game": {
            "date": str(worst["GameDate"])[:10],
            "attendance": int(worst["Attendance"]),
            "items_sold": int(worst["Qty"]),
        },
    }