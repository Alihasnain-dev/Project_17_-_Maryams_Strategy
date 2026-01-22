# Research State Log - YBI Intraday Strategy

**Last Updated**: 2026-01-22
**Current Phase**: AUDIT V5 FIXES COMPLETE - All Issues Resolved

---

## Current Research Objective

Implement and statistically validate a **no-lookahead, intraday-only** backtest of the YBI (Maryam) small-cap scalping strategy using Polygon minute-bar data.

---

## Current Status & Verdict

**Status**: V5 CORRECTIVE IMPLEMENTATION COMPLETE - All artifacts generated

**Verdict**: After fixing all V5 audit issues (missing-data handling, bootstrap consistency, true negative controls, fee modeling clarification), the implementation is methodologically sound. The strategy shows a **statistically significant negative edge**.

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

**51/51 tests passing** including:

### New Tests (V5)
- `test_block_bootstrap_with_all_trading_days()` - Verifies 0-trade days included
- `test_time_shift_negative_control()` - Validates time-shift control
- `test_shuffle_dates_negative_control()` - Validates shuffle control
- `test_negative_controls_non_degenerate()` - Ensures null has variance

### Previous Tests (V4)
- `test_block_bootstrap_basic()` - Verifies null_std > 0
- `test_block_bootstrap_detects_significant_positive_edge()` - p < 0.05
- `test_block_bootstrap_detects_significant_negative_edge()` - p < 0.05
- `test_block_bootstrap_no_edge_not_significant()` - CI includes zero
- `test_portfolio_fee_ledger_consistency()` - cash_change == realized_pnl

---

## Key Outputs & Artifacts

| Artifact | Location | Status |
|----------|----------|--------|
| Strategy code | `src/ybi_strategy/strategy/ybi_small_caps.py` | VALID |
| Backtest engine | `src/ybi_strategy/backtest/engine.py` | **FIXED** (V5) |
| Portfolio module | `src/ybi_strategy/backtest/portfolio.py` | VALID |
| Fill model | `src/ybi_strategy/backtest/fills.py` | **FIXED** (fee docs) |
| Metrics | `src/ybi_strategy/reporting/metrics.py` | VALID |
| Analysis | `src/ybi_strategy/reporting/analysis.py` | **FIXED** (true negative controls) |
| Test suite | `tests/test_strategy.py` | **51 tests passing** |
| Configuration | `configs/strategy.yaml` | VALID |
| **V4/V5 Results** | `data/results_v4/` | **COMPLETE** |

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
- [x] **True negative controls implemented** (time_shift, shuffle_dates)
- [x] **Fee modeling documented** (per-round-trip on exit)
- [x] **Backtest artifacts generated** (data/results_v4/)
- [ ] Independent code review (recommended)

---

## Session Notes

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
