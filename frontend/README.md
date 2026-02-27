# 🏒 PUCK PREP
### Save-on-Foods Memorial Centre · F&B Intelligence Platform

> Predict game-day food & beverage demand for every stand, every period — powered by 239,717 real SOFMC transactions.

---

## Architecture

```
puckprep/
├── backend/
│   ├── main.py            ← FastAPI prediction engine
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx        ← Main React app
    │   ├── api.js         ← Backend service layer
    │   ├── main.jsx       ← Entry point
    │   └── index.css      ← Global styles
    ├── index.html
    ├── vite.config.js     ← Dev proxy → backend on :8000
    └── package.json
```

---

## Quick Start

### 1 — Backend (Python)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API now live at **http://localhost:8000**
- Docs: http://localhost:8000/docs
- Test: http://localhost:8000/

---

### 2 — Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

App now live at **http://localhost:5173**

Vite proxies `/api/*` → `http://localhost:8000/*` automatically.

---

## API Endpoints

| Method | Path               | Description                        |
|--------|--------------------|------------------------------------|
| GET    | `/`                | Health check                       |
| GET    | `/teams`           | All 20 WHL team names              |
| POST   | `/forecast`        | Generate full game-day forecast    |
| GET    | `/history/summary` | Aggregated historical stats        |

### POST /forecast — Request Body

```json
{
  "opponent":          "Kamloops Blazers",
  "day_of_week":       "Friday",
  "puck_drop":         "19:05",
  "attendance":        3200,
  "predicted_outcome": "win",
  "home_support_pct":  70,
  "game_date":         "2026-03-06"
}
```

`predicted_outcome` options: `"win"` | `"loss"` | `"close"` | `"unknown"`

---

## How the Model Works

### 1. Base Demand
Each item has a **mean quantity per 100 fans** and **standard deviation**, computed from 69 real SOFMC games:

```
base_qty = (mean_per100 / 100) × attendance
```

### 2. Day-of-Week Multiplier
Real multipliers from actual per-fan averages:
- Wednesday: **1.118×** (biggest spending night)
- Saturday:  1.036×
- Friday:    1.010×
- Sunday:    0.923×
- Tuesday:   **0.876×** (quietest)

### 3. Outcome Modifier
| Outcome | Beer   | Food   | NA Bev |
|---------|--------|--------|--------|
| Win     | +18%   | +6%    | +5%    |
| Loss    | −12%   | −3%    | +2%    |
| Close   | +6%    | +2%    | +2%    |

### 4. Home Support Modifier
- 90% home crowd → +10% total demand
- 50% neutral    → ±0%
- 20% home crowd → −8% total demand

### 5. Final Formula
```
predicted = base_qty × dow_multiplier × outcome_modifier × home_support_modifier
```

### Confidence Levels
- 🟢 **High** — variance &lt;20% (Bottle Pop, Fries, Water — very predictable)
- 🟡 **Medium** — variance 20–45% (Beer, Popcorn, Churro)
- 🔴 **Low** — variance &gt;45% (Hot Dog — supply/staffing constrained, watch live)

---

## Data Foundation

| Metric                    | Value            |
|---------------------------|------------------|
| Total transactions        | 239,717          |
| Games in training set     | 69               |
| Seasons                   | 2024/25, 2025/26 |
| Attendance range          | 1,245 – 5,540    |
| Attendance → Sales R²     | **0.948**        |
| Concession stands covered | 6                |

---

## Hackathon Notes

- **Model transparency**: Every number traces back to real data. R²=0.948 is shown in the UI.
- **Small model architecture**: No GPT-4. Prediction is statistical; AI (Haiku) is only for narrative generation if integrated.
- **Stand-level granularity**: Each of the 6 SOFMC stations gets its own item-level forecast based on real historical sell-through share.
- **Win/Loss modifier**: Alcohol sales statistically spike +15–18% on winning nights — a differentiator vs. pure attendance regression.
