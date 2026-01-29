# Research State Log - YBI Intraday Strategy

**Last Updated**: 2026-01-29
**Current Phase**: V10 AUDIT FIXES COMPLETE - Ready for End-to-End Rerun

---

## Current Research Objective

Implement and statistically validate a **no-lookahead, intraday-only** backtest of the YBI (Maryam) small-cap scalping strategy using Polygon minute-bar data.

---

## Current Status & Verdict

**Status**: V10 CORRECTIVE IMPLEMENTATION COMPLETE - All 75 tests pass

**Verdict**: After fixing V10 audit issues (premarket screener selection bias, config exposure, documentation accuracy, leakage audit precision), the premarket_gap watchlist method is now deterministic and properly documented. Ready for full re-run with Polygon API.

### V10 Audit Issues (All Fixed)

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Premarket screener candidate selection bias | CRITICAL | **FIXED** | Candidates sorted by PREVIOUS DAY VOLUME (deterministic proxy) |
| max_candidates_to_scan not in config | HIGH | **FIXED** | Added to strategy.yaml and wired through engine.py |
| "TRUE premarket screener" claim misleading | HIGH | **FIXED** | Documentation updated to describe actual methodology |
| Leakage audit overstated same-bar checks | MEDIUM | **FIXED** | Narrowed claims to exactly what's checked (signal_ts ordering) |

**Premarket Screener Methodology (premarket_gap)**:
1. Get all tickers from previous day's grouped daily data
2. Filter by price range (min_prev_close to max_prev_close)
3. Apply common stock pattern filter (excludes warrants, units)
4. **Sort candidates by PREVIOUS DAY VOLUME (descending)** - deterministic proxy
5. Scan top max_candidates_to_scan for premarket data (04:00-09:29 ET)
6. Apply thresholds: min_premarket_pct, min_premarket_volume, min_premarket_dollar_volume
7. Return top_n by premarket_pct

### V9 Audit Issues (All Fixed)

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Max-trades-per-day counted at exit | CRITICAL | **FIXED** | `record_entry()` increments count; `record_exit()` does not |
| Cooldown bypass for gap-through stops | CRITICAL | **FIXED** | Cooldown triggers for `reason.startswith("stop_hit")` |
| Universe filter false positives | HIGH | **FIXED** | Ambiguous patterns (W$/P$) skipped when reference data available |
| No HAC standard errors | HIGH | **FIXED** | Added `daily_series_inference()` with Newey-West HAC SE |
| No leakage audit | HIGH | **FIXED** | Added `leakage_audit()` verifying signal_ts < entry_ts |
| Missing slippage sensitivity infrastructure | MEDIUM | **READY** | Existing `scripts/run_stress_test.py` supports 3+ scenarios |

### V8 Audit Issues (All Fixed)

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Unmatched BUY fill (CCLDP) | CRITICAL | **FIXED** | Force-flat uses per-ticker last timestamp |
| Reference filtering disabled by default | CRITICAL | **FIXED** | `use_reference_data=True` is now default |
| No open positions invariant | HIGH | **FIXED** | RuntimeError raised if positions remain open |
| Preferred stocks not filtered (CCLDP) | HIGH | **FIXED** | Added P$ pattern for preferreds |

### V8 Backtest Results (Oct 2024 - Jan 2025)

| Metric | Value |
|--------|-------|
| **Total Trades** | 328 |
| **Total P&L** | **-$6,057.00** |
| **Win Rate** | 22.3% (73W / 251L / 4BE) |
| **Expectancy** | -$18.47 per trade |
| **Mean Daily P&L** | -$81.85 |
| **Sharpe Ratio** | -13.67 |
| **Max Drawdown** | -$6,057.00 (-60.6%) |
| **p-value** | 1.17e-11 |
| **t-statistic** | -8.04 |
| **Trading Days** | 74 (3 holidays excluded) |
| **95% CI** | [-$22.56, -$14.42] (expectancy) |
| **Significant at 1%?** | Yes |
| **Reconciliation** | **PASS** ($0.00 discrepancy) |
| **Data Completeness** | 100% (0 error days) |

### V8 vs V7 Comparison

| Metric | V7 (Invalid) | V8 (Valid) |
|--------|--------------|------------|
| Total Trades | 330 | 328 |
| Reconciliation | FAIL ($2,475.32) | **PASS** ($0.00) |
| CCLDP trades | 1 (unmatched BUY) | 0 (filtered) |
| Reference filtering | Disabled | **Enabled** |

**Conclusion**: The strategy shows a **statistically significant negative edge** (p < 0.01). The V8 results are internally consistent and can be trusted for research conclusions.

### V7 Full Run Results (INVALID - for reference only)

| Metric | Value |
|--------|-------|
| Total Trades | 330 |
| Total P&L | **-$5,379.64** |
| Reconciliation | **FAIL** - CCLDP unmatched ($2,475.32 discrepancy) |

**Note**: V7 results are INVALID due to reconciliation failure. Use V8 results instead.

### Latest Backtest Results (Oct 2024 - Jan 2025) - V4/V5

| Metric | Value |
|--------|-------|
| Total Trades | 299 |
| Total P&L | **-$5,616.68** |
| Win Rate | 19.1% |
| Expectancy | -$18.78 per trade |
| Mean Daily P&L | -$72.94 |
| Sharpe Ratio | -13.86 |
| p-value (two-sided) | 9.999e-05 (bootstrap) |
| t-statistic | -7.66 |
| Trading Days | 77 (eligible days only, error days excluded) |
| 95% CI | [-$91.96, -$54.63] |
| Significant at 5%? | Yes |
| Significant at 1%? | Yes |

**Conclusion**: The strategy is NOT profitable. The negative edge is statistically significant (p < 0.01) and the 95% CI excludes zero.

---

## Audit V8 Issues (All Fixed)

Eighth audit identified critical reconciliation/ledger issues:

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Unmatched BUY fill (no SELL) | CRITICAL | **FIXED** | Force-flat uses per-ticker last timestamp |
| Reference filtering disabled by default | CRITICAL | **FIXED** | `use_reference_data=True` is now default |
| No open positions invariant | HIGH | **FIXED** | RuntimeError if positions remain open |
| Preferred stocks not filtered | HIGH | **FIXED** | Added P$ pattern for preferreds |

### 1. Force-Flat Per-Ticker Fix (FIXED)

The bug: force-flat used global `last_ts` and checked `if last_ts in df.index`. If a ticker's data ended earlier (halt, missing data), this condition failed and the position stayed open silently.

```python
# portfolio.py: BEFORE (BUG)
last_ts = sorted_timestamps[-1]  # Global last timestamp
for ticker, pp in portfolio.positions.items():
    if pp.position.is_open() and ticker in ticker_bars:
        df = ticker_bars[ticker]
        if last_ts in df.index:  # BUG: Fails if ticker data ended early!
            close_position(...)

# AFTER (FIXED)
for ticker, pp in portfolio.positions.items():
    if pp.position.is_open() and ticker in ticker_bars:
        df = ticker_bars[ticker]
        if len(df) > 0:
            # Use THIS ticker's last available bar
            ticker_last_ts = df.index[-1]
            close_position(ticker, pp, ticker_last_ts, ...)

# INVARIANT CHECK: No open positions allowed
open_positions = [(t, pp) for t, pp in portfolio.positions.items() if pp.position.is_open()]
if open_positions:
    raise RuntimeError(f"INVARIANT VIOLATION: positions still open: {open_positions}")
```

### 2. Reference Data Filtering Default (FIXED)

Pattern-only filtering missed preferreds (e.g., CCLDP). Now reference data is enabled by default:

```python
# watchlist.py: BEFORE
use_reference_data: bool = False  # Pattern filter alone misses preferreds!

# AFTER
use_reference_data: bool = True  # CRITICAL: Required to filter CCLDP etc.
```

### 3. Preferred Stock Pattern (FIXED)

Added P$ pattern to catch preferreds as a backstop:

```python
NON_COMMON_PATTERNS = [
    ...
    r"P$",  # Preferreds (P suffix after 3+ chars, e.g., CCLDP)
    ...
]
```

---

## Audit V7 Issues (All Fixed)

Seventh audit identified critical execution model issues:

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Intrabar lookahead in portfolio sizing | CRITICAL | **FIXED** | Uses bar OPEN prices for equity/sizing |
| Universe contamination (warrants/units) | CRITICAL | **FIXED** | Pattern-based common-stock filter |
| Stop-loss semantics broken | CRITICAL | **FIXED** | Entries rejected if stop >= entry_px |
| Fractional shares | HIGH | **FIXED** | int(qty) after sizing calculation |
| Holiday days included as 0-P&L | HIGH | **FIXED** | Market calendar module |

### 1. Intrabar Lookahead Fix (FIXED)

Portfolio sizing now uses prices available at bar OPEN only:

```python
# portfolio.py: New function to get prices at execution time
def get_prices_at_open() -> dict[str, float]:
    """Get prices available at bar OPEN for mark-to-market.

    CRITICAL: At bar open, we only know:
    - The current bar's OPEN price (not close/high/low)
    - Prior bars' prices (carried forward)
    """
    prices = {}
    for ticker, df in ticker_bars.items():
        if current_ts in df.index:
            # Use bar OPEN - the only price known at execution time
            prices[ticker] = float(df.loc[current_ts, "o"])
        elif ticker in last_known_prices:
            prices[ticker] = last_known_prices[ticker]
    return prices

# Usage in Phase 1 (pending signal execution):
prices_at_open = get_prices_at_open()
current_equity = portfolio.get_equity(prices_at_open)
```

### 2. Common Stock Filter (FIXED)

New module `src/ybi_strategy/universe/watchlist.py` filters out warrants, units, and OTC:

```python
NON_COMMON_PATTERNS = [
    r"\.WS$",       # Warrants (e.g., QBTS.WS)
    r"\.W$",        # Warrants (e.g., AFRM.W)
    r"\.U$",        # Units
    r"\.R$",        # Rights
    r"W$",          # Warrants (W suffix after 4+ chars, e.g., SOUNW)
    r"\^",          # Index or special symbols
]

def is_common_stock_ticker(ticker: str) -> bool:
    """Pattern-based filter for common stocks."""
    for pattern in NON_COMMON_PATTERNS:
        if re.search(pattern, ticker_upper):
            # Special handling for W suffix (allow short tickers like "W", "VW")
            if pattern == r"W$" and len(ticker_upper) <= 3:
                continue
            return False
    return True
```

### 3. Stop-Loss Semantics (FIXED)

Entries are now rejected when stop >= entry (e.g., gap-down scenarios):

```python
# portfolio.py: In pending entry execution
stop_px = pp.pending_entry.stop_base * (1.0 - stop_buffer_pct)

# CRITICAL FIX: Stop must be BELOW entry for long trades
if stop_px >= entry_px:
    pp.pending_entry = None
    continue  # Skip this entry - invalid risk

stop_distance = entry_px - stop_px  # Always positive for valid long stops
```

Gap-through-stop handling also added:

```python
# If bar opens BELOW stop (gap through), exit at open
if o <= pp.position.stop:
    exit_px = fills.apply_exit(o)  # Gap through - fill at open
    exit_reason = "stop_hit_gap_through"
else:
    exit_px = fills.apply_exit(pp.position.stop)  # Normal stop hit
    exit_reason = "stop_hit"
```

### 4. Integer Shares (FIXED)

All share quantities cast to integers:

```python
# portfolio.py: After sizing calculation
qty = int(qty)  # CRITICAL: Equities trade in whole shares only

# Also for scale-outs
take_qty = int(pp.position.qty * scale_frac)
```

### 5. Market Calendar Module (FIXED)

New module `src/ybi_strategy/calendar/market_calendar.py`:

```python
US_MARKET_HOLIDAYS: Set[date] = {
    date(2024, 11, 28),  # Thanksgiving
    date(2024, 12, 25),  # Christmas
    date(2025, 1, 1),    # New Year's Day
    # ... all NYSE/NASDAQ holidays 2024-2026
}

def is_market_holiday(d: date) -> bool:
    return d in US_MARKET_HOLIDAYS

def is_trading_day(d: date) -> bool:
    return not is_weekend(d) and not is_market_holiday(d)
```

Engine now skips holidays:

```python
# engine.py: In run() method
if is_market_holiday(d):
    day_audit.append({
        "date": d.isoformat(),
        "status": "holiday_closed",
        "reason": "US market holiday - market closed",
    })
    continue
```

---

## Audit V6 Issues (All Fixed)

Sixth audit identified critical accounting and methodology issues:

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Trade P&L omitting scale-out P&L | CRITICAL | **FIXED** | Trade record now includes `scale_pnl + final_exit_pnl - fees` |
| Fee double-counting | CRITICAL | **FIXED** | Fees applied exactly once per round-trip (on final exit only) |
| Invalid "negative controls" | HIGH | **FIXED** | Renamed to "stress_tests" with honest limitations |
| Previous trading day ignores holidays | MEDIUM | **FIXED** | Uses actual market data availability |
| No reconciliation routine | MEDIUM | **FIXED** | Added `reconcile_trades_and_fills()` |

### 1. Trade P&L Accounting (FIXED)

Trade records now include TOTAL P&L from all partial exits:

```python
# portfolio.py: close_position() now computes total P&L correctly
total_trade_pnl = pp.scale_pnl_realized + final_exit_pnl - fills.fees_per_trade

trades_out.append({
    "pnl": total_trade_pnl,        # TOTAL P&L including scale-outs
    "scale_pnl": pp.scale_pnl_realized,  # Audit: P&L from partial exits
    "final_exit_pnl": final_exit_pnl,    # Audit: P&L from final close
    ...
})
```

New trade record fields for audit trail:
- `scale_pnl`: Cumulative P&L from partial scale-outs
- `final_exit_pnl`: P&L from final position close
- `original_entry_qty`: Original position size before any scale-outs

### 2. Fee Double-Counting (FIXED)

Fees are now applied exactly ONCE per round-trip (on final exit only):

```python
# Scale-out: NO fee deduction
scale_pnl = (exit_px - pp.position.avg_entry) * take_qty
portfolio.cash += (exit_px * take_qty)  # Full proceeds, no fee
pp.scale_pnl_realized += scale_pnl

# Final exit: Fee deducted once
total_trade_pnl = pp.scale_pnl_realized + final_exit_pnl - fills.fees_per_trade
portfolio.cash += (exit_px * qty - fills.fees_per_trade)
```

### 3. Stress Tests vs Negative Controls (FIXED)

The "negative controls" have been honestly renamed to "stress tests" with clear limitations:

```python
# engine.py output structure
"stress_tests": {
    "description": "Heuristic tests that perturb realized P&L values. "
                   "LIMITATION: These do NOT resimulate the backtest with "
                   "modified entries, so they CANNOT reliably detect lookahead bias.",
    "time_shift_5min": {...},
    "shuffle_dates": {...},
}
```

For actual lookahead detection, verify:
1. `signal_ts < entry_ts` for all trades (tested in `test_no_same_bar_fills`)
2. Indicators use only past data (code review)
3. Watchlist uses only data available at selection time (code review)

### 4. Previous Trading Day (FIXED)

Now uses actual market data availability instead of just skipping weekends:

```python
def _prev_trading_day(self, d: date) -> date:
    """Get previous trading day using actual market data availability."""
    prev = d - timedelta(days=1)
    for _ in range(10):  # Max lookback
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        try:
            data = self.polygon.grouped_daily(prev)
            if data and len(data) > 0:
                return prev
        except Exception:
            pass
        prev -= timedelta(days=1)
    return prev
```

### 5. Reconciliation Routine (NEW)

Added `reconcile_trades_and_fills()` to verify trades.csv matches fills.csv:

```python
from ybi_strategy.reporting.analysis import reconcile_trades_and_fills

result = reconcile_trades_and_fills(
    trades_df, fills_df,
    tolerance=0.01,
    fees_per_trade=0.0,
)
assert result.is_consistent, f"P&L mismatch: {result.discrepancies}"
```

---

## Audit V5 Issues (All Fixed)

Fifth audit identified critical research methodology issues:

| Issue | Severity | Status | Resolution |
|-------|----------|--------|------------|
| Missing-data days treated as 0-P&L | CRITICAL | **FIXED** | Error days excluded from daily series |
| Bootstrap inconsistent with metrics | CRITICAL | **FIXED** | all_trading_days parameter added |
| Bootstrap mislabeled as "negative control" | HIGH | **FIXED** | Renamed to statistical_inference; added true negative controls |
| Fee modeling unclear | MEDIUM | **FIXED** | Documented as per-round-trip (applied on exit) |
| V4 artifacts missing | MEDIUM | **FIXED** | Backtest rerun complete |

### 1. Missing-Data Days Handling (FIXED)

Error days (API failures, timeouts) are now EXCLUDED from the daily P&L series:

```python
# engine.py: Only eligible days are included
eligible_statuses = ["ok", "no_trades", "no_watchlist"]
eligible_trading_days = audit_df[audit_df["status"].isin(eligible_statuses)]["date"].tolist()
```

New summary.json fields:
```json
{
  "day_audit": {
    "eligible_trading_days": 77,
    "days_with_errors": 0,
    "daily_series_definition": "Days with status in [ok, no_trades, no_watchlist]. Error days (API failures) are EXCLUDED as missing data, not treated as 0 P&L."
  }
}
```

### 2. Bootstrap Test Consistency (FIXED)

`block_bootstrap_test()` now accepts `all_trading_days` parameter to match `compute_metrics()`:

```python
bootstrap_result = block_bootstrap_test(
    trades_df,
    n_bootstrap=10000,
    random_seed=42,
    all_trading_days=all_trading_days,  # Include 0-trade days
)
```

**Verification**: `bootstrap.observed_mean_daily_pnl` == `metrics.mean_daily_pnl` (-$72.94)

### 3. True Negative Controls (NEW)

The bootstrap test is now correctly labeled as `statistical_inference.bootstrap_mean_test` (hypothesis test, not leakage control).

Added TRUE negative controls that break signal->return structure:

```python
# Tests that detect lookahead/leakage by degrading performance
time_shift_negative_control(trades_df, shift_minutes=5, n_simulations=1000)
shuffle_dates_negative_control(trades_df, n_simulations=1000)
```

New summary.json structure:
```json
{
  "statistical_inference": {
    "bootstrap_mean_test": {
      "description": "Day-level block bootstrap testing H0: E[daily P&L] = 0. This is a HYPOTHESIS TEST, not a leakage control.",
      "observed_mean_daily_pnl": -72.94,
      "p_value": 0.0001,
      "ci_lower_95": -91.96,
      "ci_upper_95": -54.63
    }
  },
  "negative_controls": {
    "description": "Tests that break signal->return structure. If strategy still shows edge after breaking, investigate leakage.",
    "time_shift_5min": {...},
    "shuffle_dates": {...}
  }
}
```

### 4. Fee Modeling Clarification (FIXED)

`fees_per_trade` is now explicitly documented as **per-round-trip** (applied once on exit):

```python
@dataclass
class FillModel:
    """
    FEE CONVENTION:
    - fees_per_trade: Fee applied ONCE per round-trip (on exit only).
      This represents the total cost of opening and closing a position.
    """
    fees_per_trade: float = 0.0
```

---

## Test Coverage

**75/75 tests passing** including:

### New Tests (V10 - Premarket Screener)
- `test_premarket_watchlist_item_dataclass()` - Verifies PremarketWatchlistItem fields
- `test_ambiguous_patterns_not_applied_in_premarket_screener()` - Verifies W$/P$ skipped
- `test_premarket_metrics_calculation()` - Verifies premarket return and dollar volume math
- `test_config_supports_premarket_gap_method()` - Verifies config structure for premarket_gap

### New Tests (V9)
- `test_day_risk_state_counts_at_entry()` - Verifies trade count increments at entry, not exit
- `test_cooldown_triggered_for_gap_through_stop()` - Verifies cooldown for all stop_hit* reasons
- `test_ambiguous_patterns_skipped_with_reference_data()` - Verifies W$/P$ skipped when ref data available
- `test_leakage_audit_passes_for_valid_trades()` - Verifies signal_ts < entry_ts validation passes
- `test_leakage_audit_fails_for_lookahead()` - Verifies lookahead violations detected
- `test_daily_series_inference_with_hac()` - Verifies HAC (Newey-West) standard errors computed
- `test_daily_series_inference_includes_zero_trade_days()` - Verifies 0-trade days included

### New Tests (V8)
- `test_force_flat_per_ticker_timestamp()` - Verifies force-flat uses per-ticker last bar
- `test_no_open_positions_invariant()` - Verifies open position tracking
- `test_preferred_stock_filter()` - Verifies CCLDP-style preferreds filtered
- `test_reference_data_default_enabled()` - Verifies use_reference_data=True by default

### New Tests (V7)
- `test_common_stock_filter_rejects_warrants()` - Verifies warrants/units filtered out
- `test_common_stock_filter_accepts_common()` - Verifies valid tickers allowed
- `test_market_calendar_excludes_holidays()` - Verifies holiday detection
- `test_integer_shares_only()` - Verifies all quantities are integers
- `test_stop_below_entry_for_longs()` - Verifies stop < entry for all trades
- `test_no_intrabar_lookahead_in_sizing()` - Verifies equity uses bar open prices

### New Tests (V6)
- `test_scaled_trade_pnl_includes_scale_out()` - Verifies total P&L = scale_pnl + final_exit_pnl - fees
- `test_fee_applied_once_per_round_trip()` - Verifies fees applied exactly once per trade
- `test_reconciliation_trades_match_fills()` - Verifies trades.csv matches fills.csv
- `test_reconciliation_detects_mismatch()` - Validates reconciliation catches errors

### Updated Tests (V6)
- `test_time_shift_negative_control()` - Renamed to stress test, uses perturbed_std_pnl
- `test_shuffle_dates_negative_control()` - Renamed to stress test
- `test_negative_controls_non_degenerate()` - Validates stress tests have variance
- `test_portfolio_fee_ledger_consistency()` - Updated for V6 P&L accounting

### Previous Tests (V4/V5)
- `test_block_bootstrap_basic()` - Verifies null_std > 0
- `test_block_bootstrap_detects_significant_positive_edge()` - p < 0.05
- `test_block_bootstrap_detects_significant_negative_edge()` - p < 0.05
- `test_block_bootstrap_no_edge_not_significant()` - CI includes zero
- `test_block_bootstrap_with_all_trading_days()` - Verifies 0-trade days included

---

## Key Outputs & Artifacts

| Artifact | Location | Status |
|----------|----------|--------|
| Strategy code | `src/ybi_strategy/strategy/ybi_small_caps.py` | VALID |
| Backtest engine | `src/ybi_strategy/backtest/engine.py` | VALID |
| Portfolio module | `src/ybi_strategy/backtest/portfolio.py` | **FIXED** (V9: record_entry at BUY, cooldown for all stops) |
| Fill model | `src/ybi_strategy/backtest/fills.py` | VALID |
| Metrics | `src/ybi_strategy/reporting/metrics.py` | VALID |
| Analysis | `src/ybi_strategy/reporting/analysis.py` | VALID |
| **Watchlist/Universe** | `src/ybi_strategy/universe/watchlist.py` | **FIXED** (V9: ambiguous patterns skipped with ref data) |
| **Market Calendar** | `src/ybi_strategy/calendar/market_calendar.py` | VALID |
| Polygon client | `src/ybi_strategy/polygon/client.py` | VALID |
| Test suite | `tests/test_strategy.py` | **75 tests passing** |
| Configuration | `configs/strategy.yaml` | VALID |
| **V8 Results** | `data/results_v8/` | **COMPLETE** (reconciliation verified) |
| **V7 Results** | `data/results_v7/` | **INVALID** (reconciliation failed) |
| **V6 Results** | `data/results_v6/` | COMPLETE |

---

## Research Integrity Checkpoints

- [x] Execution timing bias eliminated (next-bar fills)
- [x] Portfolio-level simulation implemented
- [x] Position sizing uses current equity (mark-to-market)
- [x] Statistics computed on daily returns including 0-trade days
- [x] **Missing-data days EXCLUDED** (not treated as 0 P&L)
- [x] Timezone handling uses pd.Timestamp.tz_localize()
- [x] Two-sided significance test
- [x] Sample size guards (N < 30 flagged)
- [x] **Bootstrap test consistent with metrics** (same day set)
- [x] **Stress tests honestly labeled** (NOT true negative controls)
- [x] **Fee modeling documented and correct** (per-round-trip on exit only)
- [x] **Trade P&L includes all partial exits** (scale_pnl + final_exit_pnl - fees)
- [x] **Previous trading day handles holidays** (uses market data availability)
- [x] **Reconciliation routine implemented** (trades.csv matches fills.csv)
- [x] **Backtest artifacts generated** (data/results_v8/ - V7 invalid)
- [x] **No intrabar lookahead** (V7: uses bar OPEN for sizing, not close)
- [x] **Universe filter** (V8: reference data + preferreds filter)
- [x] **Stop-loss semantics** (V7: stop < entry for all long entries)
- [x] **Integer shares** (V7: no fractional share quantities)
- [x] **Market calendar** (V7: holidays excluded, not treated as 0-P&L)
- [x] **Force-flat per-ticker** (V8: uses each ticker's last bar, not global)
- [x] **No open positions invariant** (V8: RuntimeError if positions remain)
- [x] **Reconciliation verified** (V8: $0.00 discrepancy, all BUYs have SELLs)
- [x] **Max-trades counted at entry** (V9: record_entry() at BUY fill, not exit)
- [x] **Cooldown for all stop exits** (V9: reason.startswith("stop_hit"))
- [x] **Universe filter no false positives** (V9: ambiguous patterns skipped with ref data)
- [x] **HAC standard errors** (V9: daily_series_inference() with Newey-West)
- [x] **Leakage audit in summary** (V9: signal_ts < entry_ts verification)
- [x] **Slippage sensitivity infrastructure** (scripts/run_stress_test.py ready)
- [x] **Premarket screener deterministic** (V10: sorted by prev day volume before truncation)
- [x] **max_candidates_to_scan exposed** (V10: in config and wired through engine.py)
- [x] **Premarket screener docs accurate** (V10: removed "TRUE" claim, documented methodology)
- [x] **Leakage audit claims accurate** (V10: narrowed to signal_ts ordering only)
- [ ] **End-to-end rerun with premarket_gap mode** (PENDING - requires Polygon API)
- [ ] Independent code review (recommended)

---

## Session Notes

**2026-01-24 (Audit V9 Fixes)**:
- Received ninth audit identifying critical/high issues:
  - Max-trades-per-day counted at exit (allowed 6-7 trades when max=5)
  - Cooldown bypass for `stop_hit_gap_through` (only checked `reason == "stop_hit"`)
  - Universe filter false positives (W$/P$ patterns rejected legitimate stocks like SNOW)
  - No HAC standard errors for daily P&L inference
  - No explicit leakage audit in summary.json
- CRITICAL FIX: Split DayRiskState into `record_entry()` and `record_exit()`
  - `record_entry()` increments trade count at BUY fill time
  - `record_exit()` records P&L and cooldown without incrementing count
- CRITICAL FIX: Cooldown now checks `reason.startswith("stop_hit")`
- HIGH FIX: Split patterns into UNAMBIGUOUS (always applied) and AMBIGUOUS (skipped with ref data)
  - UNAMBIGUOUS: .WS, .W, .U, .R, ^ (explicit suffixes)
  - AMBIGUOUS: W$, P$ (can cause false positives on SNOW, SHOP)
- HIGH FIX: Added `daily_series_inference()` with Newey-West HAC standard errors
- HIGH FIX: Added `leakage_audit()` verifying signal_ts < entry_ts for all trades
- HIGH FIX: Integrated both into engine.py summary.json output
- Slippage sensitivity infrastructure already exists (`scripts/run_stress_test.py`)
- All 71 tests pass (7 new V9 tests)
- **STATUS**: V9 code fixes complete, ready for full backtest re-run

**2026-01-29 (Audit V10 Fixes - Premarket Screener)**:
- Received tenth audit (FAIL) identifying premarket screener issues:
  - Candidate selection used arbitrary order (head(N) without sorting)
  - max_candidates_to_scan not exposed in config or recorded in metadata
  - "TRUE premarket screener" claim was misleading
  - Leakage audit claimed same-bar checks but only checked ordering
- CRITICAL FIX: Sort candidates by PREVIOUS DAY VOLUME (descending) before truncation
  - Deterministic and reproducible selection based on liquidity proxy
- HIGH FIX: Added `max_candidates_to_scan` to strategy.yaml
- HIGH FIX: Wired `max_candidates_to_scan` through engine.py to watchlist builder
- HIGH FIX: Updated documentation to accurately describe methodology
- MEDIUM FIX: Narrowed leakage_audit claims to exactly what's checked
  - Removed `same_bar_fill_violations` field (not implemented)
  - Updated docstrings to specify signal_ts ordering only
- All 75 tests pass (4 new premarket screener tests)
- **STATUS**: V10 code fixes complete
- **PENDING**: End-to-end rerun requires `POLYGON_API_KEY` environment variable
  - Run command: `PYTHONPATH=src python3 run_backtest.py --config configs/strategy.yaml --start 2024-10-01 --end 2025-01-15 --out data/results_v10`
  - Expected outputs: data/results_v10/{run_metadata.json, trades.csv, fills.csv, watchlist.csv, day_audit.csv, daily_metrics.csv, summary.json}
  - Acceptance criteria from V10 audit:
    1. max_trades <= risk.max_trades_per_day for all days
    2. reconciliation passes ($0 discrepancy)
    3. no open positions invariant holds
    4. watchlist.csv shows premarket_pct, premarket_volume, premarket_dollar_volume columns

**2026-01-24 (Audit V8 Fixes)**:
- Received eighth audit (FAIL) identifying reconciliation/ledger issues:
  - Unmatched BUY fill: CCLDP on 2024-11-12 had BUY but no SELL
  - $2,475.32 reconciliation discrepancy
  - Reference data filtering disabled by default (CCLDP slipped through)
- ROOT CAUSE: Force-flat used global `last_ts`, failed when ticker data ended early
- CRITICAL FIX: Force-flat now uses per-ticker `df.index[-1]`
- CRITICAL FIX: Added RuntimeError invariant if any position remains open
- CRITICAL FIX: Changed `use_reference_data=True` as default
- HIGH FIX: Added P$ pattern for preferred stocks (CCLDP, etc.)
- All 64 tests pass (4 new V8 tests)
- Backtest completed: 328 trades, -$6,057.00 P&L
- **RECONCILIATION VERIFIED**: $0.00 discrepancy, all BUYs have matching SELLs
- CCLDP no longer in results (filtered out by reference data + pattern)
- **STATUS**: V8 artifacts are internally consistent and decision-grade

**2026-01-24 (Audit V7 Fixes)**:
- Received seventh audit (FAIL) identifying execution model issues:
  - Intrabar lookahead: Portfolio sizing used bar close, not open
  - Universe contamination: Warrants/units (e.g., QBTS.WS, SOUNW) in watchlist
  - Stop-loss semantics: ~32% of trades had stop >= entry (invalid)
  - Fractional shares: Using float quantities instead of integers
  - Holiday days: Market-closed days included as 0-P&L
- CRITICAL FIX: Created `get_prices_at_open()` function - uses bar OPEN for equity
- CRITICAL FIX: Added common-stock filter in `watchlist.py`
- CRITICAL FIX: Reject entries when stop >= entry_px
- HIGH FIX: All quantities cast to int() after sizing
- HIGH FIX: Created `calendar/market_calendar.py` with US_MARKET_HOLIDAYS
- Added gap-through-stop handling (exit at open if bar gaps below stop)
- All 60 tests pass (6 new V7 tests)
- Backtest completed with cached data (API key required for full run)
- Results: 10 trades, -$74.45 P&L (3 trading days only)
- Note: Full backtest requires Polygon API key for uncached data
- **STATUS**: All V7 code fixes complete, verified by tests

**2026-01-22 (Audit V6 Fixes)**:
- Received sixth audit (FAIL) identifying:
  - Trade P&L omitting scale-out P&L ($826 discrepancy)
  - Fee double-counting (applied on scale-outs AND final exit)
  - Invalid "negative controls" that don't resimulate with shifted entries
  - Previous trading day ignores market holidays
- CRITICAL FIX: Added `scale_pnl_realized` tracking to PortfolioPosition
- CRITICAL FIX: Removed fee deduction from scale-outs (fees only on final exit)
- HIGH FIX: Renamed "negative_controls" to "stress_tests" with honest limitations
- MEDIUM FIX: `_prev_trading_day()` now checks actual market data availability
- MEDIUM FIX: Added `reconcile_trades_and_fills()` verification routine
- Updated `realized_pnl` to include fee deduction (ledger consistency)
- All 55 tests pass (4 new tests added)
- Backtest completed with V6 fixes
- Results: Total P&L = -$4,790.01 (299 trades, 27.1% win rate)
- ~$826 improvement over V5 due to correct scale-out P&L accounting
- **STATUS**: All V6 issues resolved, backtest complete

**2026-01-22 (Audit V5 Fixes)**:
- Received fifth audit (FAIL) identifying:
  - Missing-data days treated as 0-P&L
  - Bootstrap inconsistent with metrics mean_daily_pnl
  - Bootstrap mislabeled as "negative control"
  - Fee modeling unclear
- CRITICAL FIX: Excluded error days from eligible_trading_days
- CRITICAL FIX: Added all_trading_days parameter to block_bootstrap_test
- HIGH FIX: Added true negative controls (time_shift, shuffle_dates)
- MEDIUM FIX: Documented fee convention in FillModel
- Reran backtest - all artifacts generated
- All 51 tests pass
- **STATUS**: All V5 issues resolved

**2026-01-22 (Audit V4 Fixes)**:
- CRITICAL FIX: Replaced degenerate permutation test with block bootstrap
- CRITICAL FIX: test_no_same_bar_fills now fails if no BUY fills
- HIGH FIX: Fee ledger consistency

**2026-01-21 (Audit V3 Fixes)**:
- Fixed timezone tests to call production methods directly
- Fixed daily_metrics to include 0-trade days
- Fixed p_value serialization for very small values

**2026-01-21 (Audit V2 Fixes)**:
- Fixed timezone LMT offset bug
- Fixed position sizing to use current equity

---

*This file is the single source of truth for project state. Update after each completed task.*
