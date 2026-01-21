# Project Objective: YBI (Maryam) Intraday Strategy Implementation

## Objective
Build a **reproducible, no-lookahead** research + backtesting system that attempts to emulate **YBI’s intraday small-cap scalping workflow**, where the model:
- Identifies **daily top movers** (pre-market and/or market-open gainers).
- Uses **YBI-style confirmation** (EMA/VWAP + momentum/TTM state + level context) to select **entries/exits**.
- Trades **intraday only** (no overnight holds), primarily focused on the **9:30–10:30am ET “power hour.”**

## Definition of “Success”
- Produces an **auditable backtest** (trade-by-trade logs) that:
  - Avoids look-forward bias (signals only use information available at that timestamp).
  - Models execution conservatively (spread/slippage/halts handling).
  - Can be rerun end-to-end from raw Polygon pulls to final metrics.
- Produces a **daily scanner** that can generate a watchlist and candidate setups consistent with the YBI rules summarized in `DETAILED_YBI_STRATEGY_REPORT.md`.

## Non-Negotiable Constraints
- **No look-forward bias**:
  - Watchlists must be built from data available up to the selection time.
  - All features/indicators must be computed causally (no future bars).
- **Day trading only**:
  - Positions must be opened and closed same day.
  - Default: do not hold positions past 11:00am ET (configurable), and always flat by 4:00pm ET.
- **Risk-first**:
  - Stops are level-based (support/EMA/VWAP), not arbitrary cents.
  - Include daily max loss / max trades / cooldown rules.

## Inputs / Data
- Polygon “Stocks Advanced” data for:
  - Minute aggregates (extended + regular session)
  - (Optional) trades/quotes for spread/slippage modeling
  - Reference data for universe hygiene (exclude ETFs/OTC/etc.)
- YBI notes in this folder for rules/constraints.

## Deliverables
- A backtest engine + experiment harness with:
  - Daily mover selection
  - Indicator computation (EMA/VWAP + TTM/momentum approximation)
  - Strategy rules + position management (starter entries, scaling out, exits)
  - Results reporting
- A documented system architecture and “agent-ready” project guide in `AGENTS.md`.

