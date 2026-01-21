# Implementation Plan: YBI Intraday Strategy (Polygon-Powered)

This plan is written to produce a **working, unbiased backtest** first, then iterate toward fidelity with the YBI materials.

---

## 0) Guiding Principles (Do This or the Project Fails)

1. **Causality everywhere**: every signal uses only data available up to that timestamp.
2. **Execution realism**: small caps require spread/slippage modeling; avoid “perfect fill” illusions.
3. **Start simple, then add fidelity**: get a baseline system running end-to-end before adding complex pattern rules.
4. **Separate concerns**: data → features → signals → execution simulation → evaluation.
5. **Keep strategy modular**: “small-cap 1m YBI” should be its own strategy module; large caps can be separate.

---

## 1) Architecture Overview

### 1.1 Proposed repo layout (to create next)
- `src/`
  - `data/` (Polygon client, caching, calendar utilities)
  - `universe/` (ticker filters, corporate actions handling)
  - `features/` (EMA/VWAP/TTM/momentum, pivot levels, “room” metrics)
  - `strategy/` (entry/exit rules, position sizing, risk rules)
  - `backtest/` (event loop, fills, slippage, metrics)
  - `reporting/` (trade logs, plots, summary tables)
- `data/` (local: parquet/duckdb; gitignored)
- `notebooks/` (optional exploration; keep minimal)
- `configs/` (YAML strategy parameters)

### 1.2 Data storage choice
- **DuckDB + Parquet** is a strong default:
  - Fast analytics, simple deployment, easy incremental backfills.
- Keep raw pulls immutable; build derived feature tables separately.

---

## 2) Polygon Data Plan (Historical + Live)

### 2.1 Historical data needed for YBI small-cap strategy
- Minute bars including **extended hours** (pre-market) and regular session:
  - 04:00–09:29 ET: pre-market stats (PMH, premarket volume, gap%)
  - 09:30–11:00 ET: trading window (configurable)
- Daily bars:
  - Previous close, previous day high/low
- Reference data:
  - filter common stocks, exclude ETFs/OTC when desired

### 2.2 Practical watchlist construction (two-phase approach)

**Phase A (MVP, fast to implement, unbiased):**
- At 09:31 ET, build a watchlist from **top gap-ups at the open** using daily bars:
  - `gap_open_pct = (open_today / close_yesterday) - 1`
- Then trade using 1-minute bars starting 09:30.
- This is not a perfect “pre-market scanner,” but it’s a causal approximation that avoids scanning the entire universe.

**Phase B (High fidelity, heavier compute):**
- Use extended-hours minute bars to compute at 09:29 ET:
  - `premarket_gap_pct = (last_price_0929 / prev_close) - 1`
  - `premarket_vol`
  - `PMH/PML`
- Select top N premarket gainers with volume thresholds.
- Requires either:
  - Polygon bulk downloads, or
  - a maintained local store of minute bars for a broad universe.

### 2.3 Execution modeling (optional upgrade)
- Use trades/quotes to estimate:
  - spread at entry/exit
  - realistic slippage
- MVP approach: assume a conservative slippage model per trade (see Backtest section).

---

## 3) Feature Engineering (Causal)

### 3.1 Indicators required (approximate YBI behavior)
Compute on 1-minute bars (causally):
- `ema_8`, `ema_21`, `ema_34`, `ema_55`
- `sma_200` (and/or `ema_200`), using sufficient lookback (include premarket or prior session)
- `vwap_rth`: session VWAP starting 09:30 ET (cumulative typical price * vol / cumulative vol)

TTM/momentum approximations:
- Implement a standard **TTM Squeeze** proxy (e.g., BB vs KC + momentum histogram).
- Implement a **momentum histogram** proxy (commonly: linear regression of price deviation).
- Map to YBI states:
  - `ttm_state ∈ {strong_bull, weak_bull, weak_bear, strong_bear}`
  - `momentum_sign ∈ {bull, bear}`

### 3.2 Level generation (emulating “alerts” levels)
Derive “alert-like” levels for each ticker/day:
- Hard levels:
  - previous close
  - PMH/PML
  - PDH/PDL
  - open
  - HOD so far (rolling max), LOD so far (rolling min)
- Derived ladder:
  - round numbers (x.00/x.50)
  - pivot highs/lows (rolling fractal pivots)
  - clustered S/R zones (merge pivots within tolerance)

### 3.3 Pattern/structure features (from Basic Chart Reading + breakdowns)
- Rising support: sequence of higher pivot lows (recent window)
- Lowering resistance: sequence of lower pivot highs
- Double/triple top/bottom: pivots within tolerance band
- Failed breakout/breakdown:
  - break above level intrabar but close below (failed breakout)
  - break below level intrabar but close above (failed breakdown)

### 3.4 “Extension from 8 EMA” metric
Encode “don’t buy extended”:
- `extension = (high - ema_8) / ema_8`
- Strategy parameter: `max_extension_for_entry` (to calibrate)

---

## 4) Strategy Rules (Small Caps, 1-Minute)

Implement as a **state machine per ticker per day** (flat → entered → scaled → exited).

### 4.1 Universe filters (configurable defaults)
- Price: e.g. `$0.50–$20` (small-cap focus)
- Liquidity: premarket vol and/or first-5-min volume threshold
- Exclusions: ETFs, OTC, extreme spreads (if using quotes)

### 4.2 Macro + micro filters (from YBI)
- Macro bull (default long-only):
  - `close > ema_34` and `close > ema_55`
  - optionally `close > sma_200`
- Micro bull:
  - `close > ema_21`
  - `ttm_state in {weak_bull,strong_bull} OR (starter_entry_allowed and ttm_state==weak_bear)`
  - `momentum_sign == bull` (starter may relax, but must use tight stops)

### 4.3 Entry setups (prioritize)

**Setup A: PMH breakout + hold**
- Trigger: first close above PMH after 09:30
- Confirm:
  - not extended above ema_8
  - momentum bull
  - close above ema_21
- Entry: next bar open (or same bar close in simulation)
- Initial stop: below PMH or below the breakout candle low

**Setup B: Pullback hold (VWAP / 21 / 8)**
- After a breakout leg, wait for pullback to:
  - VWAP hold (failed breakdown), or
  - 21 EMA hold (failed breakdown), or
  - 8 EMA hold (for continuation)
- Confirm: TTM/momentum not flipping bear hard

**Setup C: Double bottom + reclaim 8 EMA**
- Identify a double bottom near a key level (VWAP/21/round number).
- Entry: reclaim above ema_8 with bull momentum.

**Setup D: Starter entry (probe)**
- Condition: price holding a key support level but TTM/momentum slightly bear.
- Size: 20–25% of normal.
- Add-to-full-size condition: TTM + momentum flip bull and price holds 8/21.

**Setup E: HOD breakout after “room” is created**
- After a pullback from HOD creates a meaningful range (“room”):
  - Enter on strong candle reclaiming 21 and with rising support.

### 4.4 Exits and scaling (YBI style)
- **Scale out**:
  - sell 50% at first meaningful resistance (nearest ladder level / pivot / HOD test)
  - then move stop to entry or to a nearby support/ema
- **Full exit triggers** (multi-signal preferred):
  - close below ema_8 (especially in squeeze moves)
  - repeated failed breakouts at a resistance
  - momentum + TTM flip bear
  - “extension + rejection” near resistance

### 4.5 Hard daily/session rules
- Only trade within:
  - `09:30–11:00 ET` (default)
  - optionally also `15:00–16:00 ET`
- Always flat by `16:00 ET`.
- Daily max loss / max trades / cooldown rules to avoid overtrading.

---

## 5) Backtesting Methodology (Avoid Look-Forward Bias)

### 5.1 Event-driven backtest (minute loop)
For each day:
1. Build watchlist using only data available up to watchlist time (Phase A or B).
2. Stream bars minute-by-minute; compute features incrementally.
3. Generate signals; place simulated orders.
4. Record fills, stops, partial exits, final exits.

### 5.2 Prevent common leaks
- Do not use “day high” unless it is “high so far.”
- Precompute indicators using only prior bars (no centered windows).
- When selecting daily movers, avoid using end-of-day performance.

### 5.3 Slippage/spread modeling (MVP defaults)
Conservative approach:
- Entry/exit price = bar close ± slippage
- Slippage model options (choose one):
  - fixed cents (by price bucket)
  - % of price
  - fraction of 1-min ATR
- Add fees/commissions if relevant.

### 5.4 Evaluation outputs
Produce:
- Trade log (CSV/Parquet): timestamped entries/exits, reason codes, features at entry.
- Summary metrics: win rate, avg win/loss, expectancy, max drawdown, profit factor.
- Stratified analysis: by gap%, premarket vol, time-of-day, setup type.

---

## 6) Calibration Loop (Make It “YBI-like”)

### 6.1 Start with a baseline, then iterate
Baseline:
- long-only
- PMH breakout + VWAP/21 pullback holds
- conservative stops + partial exits

Iterate by adding:
- “extension from 8 EMA” thresholds
- double/triple top/bottom detection for exits
- rising support gating
- starter entries + add logic

### 6.2 Human verification against examples
Use `breakdown-of-plays.pdf` examples as qualitative checks:
- does the algorithm fire near the described entries?
- do exits happen on the described weakening signals?

---

## 7) Live System (After Backtest Is Honest)

### 7.1 Live watchlist
Use Polygon snapshots/streams to:
- identify top movers premarket and into the open
- compute indicators in real time
- alert “setup ready” moments rather than auto-trading initially

### 7.2 Safety-first automation
If you later auto-execute:
- enforce max daily loss
- enforce “only trade the plan” (limited setups)
- force flat at cutoff times

---

## 8) Next Actions (Concrete Build Order)

1. Create code skeleton + config system.
2. Implement Polygon pull + local cache (minute + daily).
3. Implement watchlist builder (Phase A first).
4. Implement indicator computations (EMA/VWAP + TTM/momentum proxy).
5. Implement level generation + pattern detection.
6. Implement event-driven backtest + slippage model.
7. Run on a small date range; validate trade logs.
8. Expand date range; stratify results; iterate thresholds.

---

## 9) Reference
- Strategy/rules summary: `DETAILED_YBI_STRATEGY_REPORT.md`

