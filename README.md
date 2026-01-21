# YBI Strategy (Project 17 - Maryam's Strategy)

Start here:
- `DETAILED_YBI_STRATEGY_REPORT.md`
- `@Project_Objective_YBI_Strategy.md`
- `implementation_plan.md`
- `AGENTS.md`

## Quick Start (Backtest MVP)

Prereqs:
- Python 3.9+
- A Polygon API key in `POLYGON_API_KEY` (env var)

Install:
- `python -m pip install -r requirements.txt`
- Optional (recommended): `python -m pip install -e .`

Set env vars (PowerShell):
- `$env:POLYGON_API_KEY="YOUR_KEY_HERE"`
- Optional HTTP cache: `$env:YBI_HTTP_CACHE_DIR="data/http_cache"`

Run:
- `python run_backtest.py --start 2025-01-02 --end 2025-01-10 --out data/results`
  - Or: `python -m ybi_strategy --start 2025-01-02 --end 2025-01-10 --out data/results`

Output:
- `data/results/trades.csv`
- `data/results/fills.csv`
- `data/results/watchlist.csv`
- `data/results/summary.json`

Notes:
- Indicators are warmed using whatever premarket minute bars Polygon returns; VWAP is computed on the trading window only.
