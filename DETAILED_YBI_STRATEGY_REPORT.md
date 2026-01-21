# DETAILED YBI (Maryam) Strategy Report

This repository contains “Maryam Day Trading Notes from Discord” PDFs and supporting research notes. The core approach described across the YBI materials is **intraday-only, momentum-focused scalping/day trading**—primarily on **small caps**—using **pre-market + open movers**, **key price levels**, and a **confirmation-based indicator stack** to time entries/exits. Positions are **not held overnight**.

> Not investment advice. This is an engineering/strategy translation of the materials in this folder.

---

## 1) What YBI Is Doing (High-Level)

### 1.1 The core loop
1. **Start with movers**: stocks that have **already proven volatility** (pre-market gappers / top gainers into the open).
2. **Mark key levels**: pre-market high, high-of-day, previous day high, plus **hourly “in play / hold / R levels”** (in the Discord workflow) and other support/resistance.
3. **Wait for confirmation**: entries are taken when **micro + macro** conditions align (price relative to EMAs, VWAP, momentum/TTM state).
4. **Scalp and manage**: scale out into resistances, keep risk tight, exit on weakening signals (especially **8 EMA behavior** and failed breakouts).

### 1.2 Time horizon and intent
- **Small caps**: traded off the **1-minute** chart, typically held **~1–15 minutes** (sometimes longer only if indicators remain favorable).
- **“Power hour” focus**: the first hour after open (and sometimes the last hour) is highlighted as best volatility window.
- **No bag-holding**: the materials explicitly discourage holding losers and explicitly discourage holding these stocks overnight.

---

## 2) Universe Selection: “In Play” = Already Moving

### 2.1 The selection premise
YBI’s approach is not “scan random tickers until something works.” It assumes:
- You begin with **stocks that are already moving** (gap/momentum/volume).
- You then use the indicator + level framework to find **repeatable entry windows**.

### 2.2 Pre-market / open selection (what the system must replicate)
The implementation should:
- Build a **daily watchlist** from the **highest % gainers** in pre-market / into the open.
- Filter for “tradable” conditions (at minimum: liquidity/volume, price range, avoid extreme spreads when possible).
- Track key pre-market stats:
  - **Previous close**
  - **Pre-market high (PMH)**
  - **Pre-market volume**
  - **Gap %** (relative to previous close)

---

## 3) The Indicator Stack (Small Caps)

The small-cap documents define a specific stack and how it is used for entries/exits.

### 3.1 EMAs (trend + structure)
From `indicators-small-caps.pdf`:
- **8 EMA (yellow)**: “micro” guide; holds help you stay in; breakdowns used as sell signals; stops can be below it.
- **21 EMA (purple dashed)**: “micro” but “very accurate”; above = bull, below = bear; key for entries; “failed breakdown of 21” = long signal; “failed breakout of 21” = short signal (shorts more relevant to large caps; small-cap notes are long-biased in examples).
- **34 EMA (orange dashed)**: “macro”; long below is risky; starter can be acceptable if it holds.
- **55 EMA (cyan dashed)**: macro risk line; “long underneath this is high risk, you should not take a trade below this.”
- **200 EMA (solid light purple)**: macro regime; “do not take a trade if stock is below this” (high risk long).

Practical translation:
- **Macro bull filter**: price above (at least) **34/55** and ideally above **200**.
- **Micro bull filter**: price holding above **8/21**.

### 3.2 VWAP (institutional pivot + trap logic)
From `indicators-small-caps.pdf`:
- VWAP is used for entries:
  - **Long**: hold VWAP / failed breakdown of VWAP
  - **Short**: hold below VWAP / failed breakout of VWAP
- Interpretation: “short sellers like to short below VWAP; if it breaks above VWAP they are trapped.”

### 3.3 TTM Squeeze (key state indicator)
From `indicators-small-caps.pdf`:
- Treated as **key**.
- Above center line = bull (cyan/blue); below = bear (red/yellow).
- Color meaning:
  - **Cyan**: strong bull
  - **Blue**: weak bull
  - **Red**: strong bear
  - **Yellow**: weak bear (potential reversal signal but still risky)
- “Compression” (center line red) implies a release can be large.

### 3.4 Momentum (must be positive for safer longs)
From `indicators-small-caps.pdf` and `RISK MANAGEMENT 101.pdf`:
- Above center line = bull; below = bear.
- Longs with negative momentum are labeled **high risk**.

### 3.5 Auto support/resistance (retail levels)
From `indicators-small-caps.pdf`:
- Auto-plotted:
  - Support (pink)
  - Resistance (green)
- Used directly for entry/exit targeting and confirmation.

### 3.6 Candle coloring + EMA crossover indicator
From `indicators-small-caps.pdf`:
- Candle colors encode strength/weakness (strong bull, weak bear, oversold candle).
- “EMA crossover (yellow arrows)” refers to **8 EMA crossing above 13 EMA** as a bullish crossover signal (used with other confirmations).

---

## 4) The Price/Level Framework (Small Caps)

### 4.1 Key levels called out explicitly
From `small-caps-trading.pdf` and `FAQ.pdf`:
- **Pre-market high (PMH)**: “one of the most important resistance levels”; above it shorts are underwater; many squeezes happen above PMH; failed breakout at PMH is an exit signal.
- **After-hours high**: can be key resistance pre-market/intraday; failed breakout = exit signal.
- **High of day (HOD)**: must watch closely; break can lead to continuation; failed breakout can “lead to disaster.”
- **Previous day high**: break can squeeze prior-day shorts; failed breakout matters.

### 4.2 “In play” and “hold” numbers (Discord alert workflow)
From `small-caps-trading.pdf`, `education.pdf`, and `breakdown-of-plays.pdf`:
- Alerts provide:
  - An **“in play” number**: above it the stock is worth watching/trading.
  - A **“hold” number**: key support on pullbacks.
  - A ladder of **R levels (resistances)** updated hourly.
- Trader action:
  - **Plot levels** on chart (color coded) and update hourly.
  - Treat levels as potential entry/exit zones; confirmation still comes from indicator set.

Engineering implication:
- If you do not have the Discord alert feed, you must **derive equivalent key levels** (see Implementation section) to emulate the same structure.

---

## 5) Entry Logic: “Macro Bull + Micro Bull” + Key-Level Context

### 5.1 The central rule: macro first, then micro
From `breakdown-of-plays.pdf` / `education.pdf`:
- “The stock needs to be macro bull and micro bull.”
- Macro bull example criteria:
  - above 21/34/55
  - above 200 SMA
- Micro bull example criteria:
  - close to / holding 8 EMA
  - TTM bull + Momentum bull

### 5.2 Example entry archetypes (from SNSS breakdown)
From `education.pdf` (SNSS example):
- Hold of in-play number with bull indicators.
- Holds of prior resistance now acting as support.
- **Break of PMH** + alert resistance with strong bull indicators.
- Double-bottom + reclaim 8 EMA.
- VWAP + 21 EMA hold (riskier if TTM/Momentum slightly bear → can be a **starter**).
- 8/21 hold while lower indicators flip back bull (add to starter).

### 5.3 “The Magic 3” framing
From `breakdown-of-plays.pdf` (STAI breakdown):
1. **Rising support**
2. **Entry off 21 MA**
3. **TTM light blue or yellow** (light blue higher probability; yellow = reversal hint but still risky)

This is not presented as the only method, but as a strong mental model for aligning conditions.

---

## 6) Avoiding Bad Entries (Key Nuances)

### 6.1 Do not buy when extended from the 8 EMA
From `small-caps-trading.pdf`:
- A significant gap between candle high and the 8 EMA implies likely pullback toward 8 EMA.
- “You should NEVER buy the stock in this situation… I use the extension above the 8EMA as a reason to EXIT.”

### 6.2 Big sell-off candles are not random
From `small-caps-trading.pdf`:
Common precursors:
- Sideways too long without breaking resistance
- Multiple rejections at resistance
- Failed breakout of resistance
- Double/triple/quad tops

These are “structure warnings” that should be encoded as:
- “don’t chase into resistance”
- “tighten exits when repeated failures occur”

### 6.3 Patience + confirmation
From `education.pdf`:
- Alerts provide potential levels; the “perfect” entry/exit is the one **confirmed** by the indicator set.
- Don’t trade something just because it is mentioned; wait for the chart to confirm.

---

## 7) Exit Logic: Levels First, Then Indicators

### 7.1 Resistance levels are targets even if indicators are bullish
From `small-caps-trading.pdf`:
- “Resistance lines should always be your target for exiting… regardless of whether you have bullish indicators or not.”

### 7.2 The 8 EMA in squeeze/vertical moves
From `small-caps-trading.pdf`:
- In vertical moves, price often holds above 8 EMA.
- “The first candle to close below the 8 EMA is the signal to sell.”

### 7.3 Multi-signal exits (preferred)
From `small-caps-trading.pdf`:
Examples:
- Extended above 8 EMA while failing resistance
- Failing resistance with red bearish candles
- TTM turning negative with 8 EMA crossing below 21 EMA
- Momentum + TTM negative with red bearish candles

---

## 8) Position Management and Risk Rules

### 8.1 Starter entries (risk-reduced probing)
From `small-caps-trading.pdf`:
- Starter = **20–25%** normal size when price holds a key level but indicators are bearish.
- Add to full size once indicators flip bullish.
- Stop must be tight (below candle low where it held the key level).

### 8.2 Scaling out / partial profits
From `small-caps-trading.pdf`:
- Common pattern: sell **≥50%** at first resistance target.
- Then move stop to entry or nearby support.
- Continue to next resistances or exit on bearish signals.

### 8.3 Stops are level-based, not arbitrary cents
From `RISK MANAGEMENT 101.pdf` and `A_Guide_on_Trader_Psychology.pdf`:
- Stops below:
  - hold/in-play numbers
  - recent support
  - moving averages (8/21/34)
  - PMH (if acting as support), etc.
- Do not use arbitrary “5c/10c” stops; use chart structure.

### 8.4 Daily discipline rules (operational constraints)
From `RISK MANAGEMENT 101.pdf`, `A_Guide_on_Trader_Psychology.pdf`, `small-caps-trading.pdf`:
- Don’t watch P&L; trade the chart.
- Avoid overtrading/revenge trading.
- Set a realistic daily profit target; stop trading once hit.
- “Hope & denial is not a strategy.”
- Do not hold these stocks overnight.

---

## 9) Large Caps (Secondary Track)

The folder also includes a large-caps framework; it is more multi-timeframe and includes long/short setups.

From `how-to-trade-large-caps.pdf`:
- **Timeframes**:
  - Daily: plot key S/R
  - 15-min: bias (above 21 EMA = long bias; below = short bias)
  - 2-min: execution
- **Setups**:
  - Buy/sell setups (holds above/below 21 EMA)
  - Bull180/Bear180
  - Power candle
  - Failed breakout/breakdown
  - Breakout/breakdown
  - Counter-trend extension into S/R (rare; scalp only)
- **Nuances**:
  - 21 EMA slope defines trend; flat = wait for breakout/breakdown.
  - Avoid major economic news gamble.

If the project focus is “Maryam scalping/day trading gappers,” large caps can be implemented later as a separate strategy module.

---

## 10) Translating YBI Into a Testable System (Key Engineering Challenges)

### 10.1 The biggest missing piece: alert-derived levels
Many examples use “in play / hold / R” numbers provided by Discord alerts. If you don’t have that feed:
- You must create a **surrogate level generator** that yields similar “ladder” levels.

Good approximations (in order of fidelity):
1. **Pre-market + prior-day derived levels**: PMH/PML, PDH/PDL, prev close, gap fill midpoint, session open.
2. **Round-number ladder**: whole/half-dollar levels (especially on sub-$20 small caps).
3. **Pivot-based levels**: rolling local highs/lows; clustered levels.
4. **Volume profile / VWAP bands**: more advanced; closer to “where participants are stuck.”

### 10.2 Custom indicators vs. standard definitions
The YBI stack includes TOS custom indicators (TTM squeeze/momentum variants, candle coloring, auto S/R). For backtesting:
- Implement **standard** versions first (e.g., common TTM squeeze formulas).
- Then iterate to match the behavior (calibration phase).

### 10.3 Execution realism (small caps are harsh)
Small-cap backtests that assume perfect fills are usually fake. Your backtest must model:
- Spread + slippage (often large)
- Liquidity constraints
- Halts (at least conservative handling)

---

## 11) Polygon Data: What You’ll Use It For

From `POLYGON_API_KEY_ADVANCED_DATA.md`:
- Minute aggregates (and potentially second aggregates)
- Trades/quotes for more realistic execution modeling
- Reference data to build and filter the universe
- Indicators endpoints (optional) vs. local indicator computation

Important operational note:
- Keep the API key **out of git** and out of logs; use an environment variable.

---

## 12) Source Index (What Each File Contributes)

### Core YBI small-cap strategy
- `small-caps-trading.pdf`: 1-minute focus, 8 EMA rules, key levels, starter entries, scaling out, exits, stops, “no overnight.”
- `indicators-small-caps.pdf`: the exact indicator stack and how to interpret each component.
- `breakdown-of-plays.pdf`: concrete, timestamped examples translating alerts + indicators into entries/exits; includes “Magic 3” framing.
- `Basic Chart Reading.pdf`: pattern language (double tops/bottoms, failed breakouts/breakdowns, rising support).
- `RISK MANAGEMENT 101.pdf`: macro filters, starter sizing, and practical stop/target discipline.
- `A_Guide_on_Trader_Psychology.pdf`: behavioral rules that materially affect system outcomes (overtrading, FOMO, bag-holding).
- `FAQ.pdf`: definitions used in alerts workflow (PMH importance, SSR, order types, “power hour,” etc.).

### Setup / tooling (TOS-focused)
- `charting-software-setup.pdf`: why TOS; real-time requirement; options to get it.
- `ThinkorSwim-large-caps-setup.pdf`: large-cap/futures workspace + study links; daily EMA/SMA S/R overlay explanation.
- `how-to-trade-large-caps.pdf`: multi-timeframe large-cap playbook.
- `alerts-premarket.pdf`, `alerts-intraday.pdf`, `alerts-intraday  glossary  large caps setup.pdf`: alert workflow + glossary; some pages appear image-based and may not extract cleanly as text.

### Supporting research notes (non-YBI)
- `99 Day Trading Strategy Deep Dive.md`: broad day-trading concepts; complements risk/market-structure context.
- `99 GemDeepSearch Day Trading Strategy Deep Dive.md`: similar broad synthesis; includes scanning + workflow concepts.
- `99 Mastering Day Trading and Algorithmic Trading Tools with Python.md`: systems-building notes (scanners, backtesting, slippage modeling).

---

## 13) What To Build Next

If your goal is a faithful strategy implementation:
1. Build a **daily mover scanner** (pre-market and/or first 5 minutes after open).
2. Compute the YBI indicator stack (or close approximations).
3. Generate surrogate “alert-like” S/R ladders.
4. Implement a conservative backtest (minute-level, slippage + spread).
5. Iterate: compare trades to breakdown examples, calibrate thresholds.

The detailed engineering plan is in `implementation_plan.md`.

