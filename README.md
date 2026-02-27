# VIC SAVE PUCK

AI-powered F&B demand forecasting and real-time prep optimization for Save on Foods Memorial Centre (WHL Victoria Royals).

## The Problem

Arena F&B operations face three costly pain points:
- **Long lines** — fans miss game action, lowering satisfaction
- **Lost sales revenue** — understocked items mean missed transactions
- **Wasted product** — overprepped perishables go straight to the bin

## What It Does

VIC SAVE PUCK uses 240K POS transactions across 67 games (2 WHL seasons) to:

1. **Forecast demand** per stand, item, and time window before each game
2. **Generate prep plans** calibrated by perishability tier (shelf-stable 95%, medium 85%, short-life 75%)
3. **Detect drift in real-time** during the game via traffic-light monitoring (green/yellow/red)
4. **Explain drift with AI reasoning** — Claude Haiku classifies the cause and recommends corrective actions
5. **Produce post-game reports** with learnings that feed back into future forecasts

## Architecture

```
CSV Transactions + GameDetails.xlsx
         │
     Loader (parse, normalize, parquet cache)
         │
    Enricher (archetype, weather, promo flags)
         │
   Profiles (3 crowd archetypes × stand × item curves)
         │
  Forecast Engine (profile match + attendance scale + temp adjust)
         │
    Prep Plan (perishability-tiered targets)
         │
  ┌──────┴──────┐
  │  Real-Time   │
  │  Simulation  │
  │  (WebSocket) │
  └──────┬──────┘
         │
  Drift Detector → Traffic Light Monitor
         │
  AI Reasoning (Claude Haiku) → Corrective Actions
         │
  Post-Game Report + Event Optimizer
```

### Crowd Archetypes

The system classifies each game into one of three crowd profiles based on historical purchasing patterns:

| Archetype | Signature | Trigger |
|-----------|-----------|---------|
| Beer Crowd | High alcohol share, bar-heavy | Beer % ≥ 25% of transactions |
| Family | High food/NA beverage share | Beer % < 19% |
| Mixed | Balanced across categories | Everything else |

Each archetype has distinct demand curves per stand, item, and time window (pre-game, P1, INT1, P2, INT2, P3).

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend API | FastAPI + Uvicorn, WebSocket for real-time simulation |
| Forecast Engine | Pandas, NumPy, scikit-learn (bias correction) |
| AI Reasoning | Anthropic Claude (claude-haiku-4-5) with rule-based fallback |
| Data | CSV/Excel → Parquet cache (PyArrow) |
| Frontend | React 18 + Vite, Recharts, Framer Motion |
| CLI | Rich terminal output, `uv` package manager |

## Project Structure

```
VIC_SAVE_PUCK/
├── backend/
│   ├── main.py                  # FastAPI app (API + WebSocket endpoints)
│   ├── engine/
│   │   ├── config.py            # Constants, thresholds, stand metadata
│   │   ├── data/
│   │   │   ├── loader.py        # Transaction & game data loading
│   │   │   ├── enricher.py      # Game enrichment (archetype, weather, promos)
│   │   │   └── profiles.py      # Historical crowd profile builder
│   │   ├── models/
│   │   │   ├── forecast.py      # Profile-matching forecast engine
│   │   │   ├── prep_plan.py     # Perishability-based prep targets
│   │   │   ├── drift.py         # Real-time drift detection
│   │   │   ├── correction.py    # Bias correction (trained on backtest residuals)
│   │   │   └── traffic_light.py # Green/yellow/red status monitor
│   │   ├── simulator/
│   │   │   ├── engine.py        # Configurable-speed game replay
│   │   │   └── scenarios.py     # 5 demo scenarios
│   │   ├── ai/
│   │   │   ├── reasoning.py     # Claude Haiku drift classification
│   │   │   ├── post_game.py     # Post-game analysis report
│   │   │   └── event_optimizer.py # Promo opportunity analysis
│   │   └── validation/
│   │       └── backtest.py      # Leave-one-out backtest
│   └── data/                    # 15 months of POS CSVs + GameDetails.xlsx
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main app (Forecast, Simulation, Backtest, Events tabs)
│   │   ├── SimulationView.jsx   # Real-time game replay dashboard
│   │   ├── BacktestView.jsx     # Historical validation results
│   │   ├── EventView.jsx        # Promo/event recommendations
│   │   └── api.js               # API client + WebSocket handler
│   └── vite.config.js
│
├── src/vic_save_puck/           # CLI package (alternative to web UI)
│   ├── demo.py                  # CLI runner (sim | events subcommands)
│   └── ...                      # Mirror of backend/engine modules
│
├── docs/
│   ├── brief.md
│   └── HACKATHON_JUDGING_CRITERIA.md
│
└── pyproject.toml
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check + model metadata |
| `/teams` | GET | WHL team roster |
| `/forecast` | POST | Generate demand forecast for a game |
| `/history/summary` | GET | Dataset stats (games, transactions, R², location shares) |
| `/scenarios` | GET | List available simulation scenarios |
| `/ws/simulation` | WebSocket | Real-time game replay with drift + AI reasoning |
| `/validation/backtest` | GET | Leave-one-out backtest results |
| `/ai/event-recommendations` | GET | Promo optimization recommendations |

## Getting Started

### Prerequisites

- Python 3.12+ (backend)
- Node.js 18+ (frontend)
- [uv](https://docs.astral.sh/uv/) package manager (recommended)
- Anthropic API key (optional — falls back to rule-based reasoning without it)

### Backend

```bash
cd backend
pip install -r requirements.txt  # or use uv
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # runs on localhost:5173, proxies /api to :8000
```

### CLI (alternative)

```bash
# From project root
uv run python -m vic_save_puck sim --scenario normal --skip-ai
uv run python -m vic_save_puck events --skip-ai
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude API access for AI reasoning | None (rule-based fallback) |

## Simulation Scenarios

Five pre-built scenarios demonstrate the system under different conditions:

| Scenario | What It Tests |
|----------|--------------|
| `normal` | Typical game — baseline forecast accuracy |
| `untagged_promo` | Surprise demand spike from an unannounced promotion |
| `stand_redistribution` | Traffic shifts between stands mid-game |
| `weather_surprise` | Unexpected weather change affects demand mix |
| `playoff` | High-intensity playoff game with elevated demand |

## Data

- **240K+ POS transactions** across 15 monthly CSV files (Sep 2024 – Feb 2026)
- **67 games** with metadata (opponent, attendance, day of week, puck drop time)
- **6 stands**: Island Canteen, ReMax Fan Deck, TacoTacoTaco, Portable Stations, Island Slice, Phillips Bar
- Parquet caching in `data/.cache/` for fast repeated loads

## Key Design Decisions

- **Profile-matching over per-capita models** — captures crowd behavior patterns better than simple scaling
- **Claude Haiku for AI reasoning** — cost-efficient ($0.25/1M input tokens) with rule-based fallback when the API is unavailable
- **Three perishability tiers** — balances waste reduction against stockout risk per item category
- **Traffic light system** — combines volume (±15%), mix (±10%), and timing (±20%) drift into an actionable 3-color status
- **Leave-one-out backtest** — validates forecast accuracy by holding out each game and predicting from the rest

## Business Impact

- **Reduced waste** through perishability-aware prep targets
- **Fewer stockouts** via real-time drift detection and corrective actions
- **Faster service** by pre-positioning inventory based on predicted demand curves
- **Data-driven staffing** aligned to forecasted demand by stand and time window
