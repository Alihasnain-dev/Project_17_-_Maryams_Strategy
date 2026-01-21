# AGENTS.md (for Codex / Claude / Gemini / other coding agents)

## Project Summary
Implement and backtest an **intraday-only, no-lookahead** version of the **YBI (Maryam) small-cap scalping strategy** described in the PDFs in this folder.

Key constraints:
- **Day trading only**: no overnight holds.
- **Mover-first**: each day, start from pre-market / market-open gainers.
- **Confirmation-based**: entries/exits require EMA/VWAP + TTM/momentum state + key levels.
- **No look-forward bias**: every signal must be causal.

Primary reference docs:
- `DETAILED_YBI_STRATEGY_REPORT.md`
- `small-caps-trading.pdf`
- `indicators-small-caps.pdf`
- `breakdown-of-plays.pdf`
- `Basic Chart Reading.pdf`
- `RISK MANAGEMENT 101.pdf`

Polygon note:
- API key exists locally in `POLYGON_API_KEY_ADVANCED_DATA.md`; treat as a **secret** and never print or commit it.
  - Use `POLYGON_API_KEY` env var (see `.env.example`).
  - Optional response cache: set `YBI_HTTP_CACHE_DIR` (e.g. `data/http_cache`).

---

## What “Correct” Means Here

### Non-negotiable correctness criteria
- Watchlist selection is built using only data known at selection time (premarket or early-open window).
- Indicators are computed causally (no future bars, no centered windows).
- Backtest uses conservative fills (spread/slippage) and produces trade logs with reason codes.

### Strategy scope
- MVP should be **small caps, long-only**, 1-minute bars, focus 09:30–11:00 ET.
- Large caps strategy is separate and optional later (`how-to-trade-large-caps.pdf`).

---

## Implementation Checklist (Agent Tasks)

### 1) Repo scaffolding
- Create `src/` modules: data, features, strategy, backtest, reporting.
- Add `configs/strategy.yaml` with thresholds (extension, filters, time windows, slippage).
- Add `.gitignore` for `data/`, secrets, caches.

### 2) Data layer (Polygon)
- Implement:
  - minute bars (extended + regular session)
  - daily bars (prev close, PDH/PDL)
  - reference ticker filters (exclude ETFs/OTC if desired)
- Add local caching (DuckDB/Parquet preferred).

### 3) Watchlist builder (no lookahead)
Two options:
- Phase A (fast): top gap-ups at open using daily open vs prev close (available at 09:30+).
- Phase B (fidelity): top premarket gainers using 04:00–09:29 minute bars (requires broader data).

### 4) Features
Implement:
- EMA(8/21/34/55), SMA/EMA(200), RTH VWAP
- TTM squeeze proxy + momentum proxy (map to bull/bear states)
- Key levels: PMH/PML, PDH/PDL, open, HOD-so-far, pivots, round numbers
- Pattern rules: rising support, double tops/bottoms, failed breakout/breakdown
- Extension-from-EMA8 metric

### 5) Strategy + backtest
Implement:
- Setup A: PMH breakout + hold
- Setup B: pullback hold (VWAP/21/8)
- Starter entry + add logic (20–25% size) as optional toggle
- Scaling out (≥50% at first resistance)
- Exits on close below EMA8 / TTM+momentum bear / failed breakout at resistance
- Backtest event loop (minute-by-minute), with slippage model and trade log output

### 6) Validation workflow
- Run on a small date range and a small watchlist size.
- Compare a few sampled trades against the qualitative examples in `breakdown-of-plays.pdf`.
- Expand range; report stratified metrics.

---

## Do/Don’t Rules for Agents

### Do
- Keep changes minimal and modular.
- Parameterize thresholds (no hard-coded magic numbers).
- Log decisions with reason codes so we can debug why trades happen.
- Prefer running the MVP backtest via `python -m ybi_strategy --start YYYY-MM-DD --end YYYY-MM-DD`.

### Don’t
- Don’t leak secrets (Polygon API key) in output, logs, or commits.
- Don’t use future data (including “today’s high” unless it’s “high so far”).
- Don’t assume perfect fills; always model slippage/spread conservatively.
