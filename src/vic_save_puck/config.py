"""Constants, perishability tiers, stand metadata, and shared configuration."""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

PARQUET_CACHE = CACHE_DIR / "transactions.parquet"
GAMES_CACHE = CACHE_DIR / "games.parquet"
ENRICHED_CACHE = CACHE_DIR / "enriched.parquet"
PROFILES_CACHE = CACHE_DIR / "profiles.parquet"

# ── Venue ────────────────────────────────────────────────────────────────────
VENUE_LAT = 48.4284  # Save on Foods Memorial Centre, Victoria BC
VENUE_LON = -123.3656

# ── Stands ───────────────────────────────────────────────────────────────────
STANDS = [
    "SOFMC Island Canteen",
    "SOFMC ReMax Fan Deck",
    "SOFMC TacoTacoTaco",
    "SOFMC Portable Stations",
    "SOFMC Island Slice",
]

STAND_SHORT = {
    "SOFMC Island Canteen": "Island Canteen",
    "SOFMC ReMax Fan Deck": "ReMax Fan Deck",
    "SOFMC TacoTacoTaco": "TacoTacoTaco",
    "SOFMC Portable Stations": "Portable Stations",
    "SOFMC Island Slice": "Island Slice",
}

# ── Category normalisation ───────────────────────────────────────────────────
# Raw categories vary across CSVs; map to a consistent set
CATEGORY_MAP = {
    "Beer": "Beer",
    "Wine, Cider & Coolers": "Wine/Cider",
    "Liquor": "Liquor",
    "Food": "Food",
    "Snack": "Snacks",
    "Snacks": "Snacks",
    "Sweets": "Sweets",
    "NA Bev": "NA Bev",
    "NA Bev PST Exempt": "NA Bev",
    "Extras": "Extras",
}

SUPER_CATEGORIES = {
    "Beer": "Alcohol",
    "Wine/Cider": "Alcohol",
    "Liquor": "Alcohol",
    "Food": "Food",
    "Snacks": "Food",
    "Sweets": "Food",
    "NA Bev": "Beverage",
    "Extras": "Other",
}

# ── Perishability tiers ──────────────────────────────────────────────────────
PERISHABILITY = {
    # Shelf-stable: pre-stage at T-2hrs
    "shelf_stable": [
        "Candy", "Chips", "Gummies", "Cookies & Brownies", "Bottle Pop",
        "Water", "Cans of Beer", "Cider & Coolers",
        "Wine by the Glass SOFMC",
    ],
    # Medium-hold: batch at T-1hr, refresh at intermissions
    "medium_hold": [
        "Popcorn", "Hot Dog", "Dogs", "Pretzel", "Churro",
        "Cotton Candy", "Hot Drinks", "Non-Alcoholic Beverages",
        "Draught Beer", "Coffee & Baileys", "Tequila Slushy",
        "Virgin Slushy",
    ],
    # Short-life: continuous cook, with stop-prep signals
    "short_life": [
        "Fries", "Sweet Potato Fries", "Tacos", "Pizza Slice",
        "Chicken Tenders", "Burgers", "Crispy Chicken Burger",
        "Panini", "Jalapeno Poppers", "Paletas",
    ],
}

# ── Prep target percentages (asymmetric loss: waste > stockout) ──────────────
# We deliberately underpredict. Being short means slower service (recoverable).
# Being over means thrown-out food (pure waste, $$ loss).
#
# These are the fraction of forecast to actually prep.
# The drift engine then signals when to scale up if actuals exceed prep.
PREP_TARGET = {
    "shelf_stable": 0.95,   # low waste risk, prep 95% — restocking is the cost
    "medium_hold": 0.85,    # moderate waste risk, prep 85% — refresh at intermissions
    "short_life": 0.75,     # high waste risk, prep only 75% — cook more on demand
}

# When drift shows demand exceeding prep target, scale up by this increment
PREP_SCALEUP_INCREMENT = {
    "shelf_stable": 0.10,   # bump 10% at a time
    "medium_hold": 0.15,    # bump 15% — batches are chunky
    "short_life": 0.20,     # bump 20% — fast response, small batches
}

# Invert for quick lookup
ITEM_PERISHABILITY: dict[str, str] = {}
for tier, items in PERISHABILITY.items():
    for item in items:
        ITEM_PERISHABILITY[item] = tier

# ── Crowd archetypes ─────────────────────────────────────────────────────────
# Thresholds for beer_share of total alcohol+food qty
ARCHETYPE_THRESHOLDS = {
    "beer_crowd": 0.25,   # beer_share >= 25% (top quartile)
    "family": 0.19,       # beer_share < 19% (bottom quartile)
    # "mixed" is between 19-25%
}

# ── Game clock ───────────────────────────────────────────────────────────────
# Typical WHL game timeline (minutes from puck drop)
PERIOD_BOUNDARIES = {
    "P1_start": 0,
    "P1_end": 20,
    "INT1_start": 20,
    "INT1_end": 38,
    "P2_start": 38,
    "P2_end": 58,
    "INT2_start": 58,
    "INT2_end": 76,
    "P3_start": 76,
    "P3_end": 96,
}

# 10-minute time windows relative to puck drop
TIME_WINDOWS = list(range(-30, 120, 10))  # -30 to +110 in 10-min buckets

# ── WHL opponent metadata (distance from Victoria in km) ─────────────────────
OPPONENT_DISTANCE = {
    "Tri-City": 520, "TriCity": 520,
    "Wenatchee": 450,
    "Prince Albert": 2100,
    "Moose Jaw": 2000,
    "Saskatoon": 2100,
    "Kamloops": 600,
    "Seattle": 180,
    "Regina": 2200,
    "Kelowna": 480,
    "Vancouver": 110,
    "Prince George": 900,
    "Everett": 200,
    "Brandon": 2300,
    "SWC": 0,  # Swift Current / special event
    "Portland": 500,
    "Spokane": 580,
    "Penticton": 440,
    "Medicine Hat": 1500,
    "Edmonton": 1150,
    "Lethbridge": 1400,
    "Red Deer": 1250,
    "Calgary": 1100,
}

OPPONENT_DIVISION = {
    "Tri-City": "US", "TriCity": "US",
    "Wenatchee": "US",
    "Seattle": "US",
    "Everett": "US",
    "Portland": "US",
    "Spokane": "US",
    "Kamloops": "BC",
    "Kelowna": "BC",
    "Vancouver": "BC",
    "Prince George": "BC",
    "Penticton": "BC",
    "Prince Albert": "East",
    "Moose Jaw": "East",
    "Saskatoon": "East",
    "Regina": "East",
    "Brandon": "East",
    "SWC": "East",
    "Medicine Hat": "Central",
    "Edmonton": "Central",
    "Lethbridge": "Central",
    "Red Deer": "Central",
    "Calgary": "Central",
}

# ── Drift thresholds ─────────────────────────────────────────────────────────
DRIFT_VOLUME_THRESHOLD = 0.15      # 15% overall volume deviation
DRIFT_MIX_THRESHOLD = 0.10         # 10pp category mix shift
DRIFT_TIMING_THRESHOLD = 0.20      # 20% timing curve deviation
DRIFT_MIN_SAMPLES = 5              # minimum transactions before flagging
