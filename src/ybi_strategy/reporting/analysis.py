"""Stratified analysis, Monte Carlo simulation, and walk-forward validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ybi_strategy.reporting.metrics import compute_metrics, PerformanceMetrics


@dataclass
class StratifiedAnalysis:
    """Results of stratified performance analysis."""

    by_gap_bucket: dict[str, PerformanceMetrics] = field(default_factory=dict)
    by_time_of_day: dict[str, PerformanceMetrics] = field(default_factory=dict)
    by_ttm_state: dict[str, PerformanceMetrics] = field(default_factory=dict)
    by_day_of_week: dict[str, PerformanceMetrics] = field(default_factory=dict)
    by_exit_reason: dict[str, PerformanceMetrics] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "by_gap_bucket": {k: v.to_dict() for k, v in self.by_gap_bucket.items()},
            "by_time_of_day": {k: v.to_dict() for k, v in self.by_time_of_day.items()},
            "by_ttm_state": {k: v.to_dict() for k, v in self.by_ttm_state.items()},
            "by_day_of_week": {k: v.to_dict() for k, v in self.by_day_of_week.items()},
            "by_exit_reason": {k: v.to_dict() for k, v in self.by_exit_reason.items()},
        }

    def summary_table(self) -> pd.DataFrame:
        """
        Create summary table of stratified results.

        The table includes a 'sample_adequate' column that flags buckets
        with insufficient sample size (N < min_sample_threshold).
        Metrics from insufficient samples should not be used for conclusions.
        """
        rows = []

        for category, metrics_dict in [
            ("gap_bucket", self.by_gap_bucket),
            ("time_of_day", self.by_time_of_day),
            ("ttm_state", self.by_ttm_state),
            ("day_of_week", self.by_day_of_week),
            ("exit_reason", self.by_exit_reason),
        ]:
            for name, m in metrics_dict.items():
                rows.append({
                    "category": category,
                    "name": name,
                    "trades": m.total_trades,
                    "sample_adequate": not m.insufficient_sample,
                    "sample_warning": m.sample_size_warning,
                    "win_rate": m.win_rate if not m.insufficient_sample else None,
                    "avg_pnl": m.avg_pnl if not m.insufficient_sample else None,
                    "total_pnl": m.total_pnl,  # Raw P&L always shown
                    "profit_factor": m.profit_factor if not m.insufficient_sample else None,
                    "expectancy": m.expectancy if not m.insufficient_sample else None,
                })

        return pd.DataFrame(rows)


@dataclass
class MonteCarloResult:
    """Results from Monte Carlo simulation."""

    n_simulations: int = 0
    n_trades: int = 0  # Number of trades in the original sample
    original_total_pnl: float = 0.0

    # Sample size adequacy
    insufficient_sample: bool = False
    sample_size_warning: str = ""

    # Distribution of final P&L
    mean_final_pnl: float = 0.0
    median_final_pnl: float = 0.0
    std_final_pnl: float = 0.0
    pnl_5th_percentile: float = 0.0
    pnl_25th_percentile: float = 0.0
    pnl_75th_percentile: float = 0.0
    pnl_95th_percentile: float = 0.0

    # Distribution of max drawdown
    mean_max_drawdown: float = 0.0
    median_max_drawdown: float = 0.0
    max_drawdown_95th_percentile: float = 0.0

    # Risk metrics
    probability_of_profit: float = 0.0
    probability_of_ruin: float = 0.0  # P(drawdown > threshold)
    var_95: float = 0.0  # Value at Risk (5th percentile of returns)
    cvar_95: float = 0.0  # Conditional VaR (expected loss below VaR)

    # Confidence interval for expectancy
    expectancy_ci_lower: float = 0.0
    expectancy_ci_upper: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "n_simulations": self.n_simulations,
            "n_trades": self.n_trades,
            "insufficient_sample": bool(self.insufficient_sample),
            "sample_size_warning": self.sample_size_warning,
            "original_total_pnl": round(self.original_total_pnl, 2),
            "mean_final_pnl": round(self.mean_final_pnl, 2),
            "median_final_pnl": round(self.median_final_pnl, 2),
            "std_final_pnl": round(self.std_final_pnl, 2),
            "pnl_5th_percentile": round(self.pnl_5th_percentile, 2),
            "pnl_25th_percentile": round(self.pnl_25th_percentile, 2),
            "pnl_75th_percentile": round(self.pnl_75th_percentile, 2),
            "pnl_95th_percentile": round(self.pnl_95th_percentile, 2),
            "mean_max_drawdown": round(self.mean_max_drawdown, 2),
            "median_max_drawdown": round(self.median_max_drawdown, 2),
            "max_drawdown_95th_percentile": round(self.max_drawdown_95th_percentile, 2),
            "probability_of_profit": round(self.probability_of_profit, 4),
            "probability_of_ruin": round(self.probability_of_ruin, 4),
            "var_95": round(self.var_95, 2),
            "cvar_95": round(self.cvar_95, 2),
            "expectancy_ci_lower": round(self.expectancy_ci_lower, 4),
            "expectancy_ci_upper": round(self.expectancy_ci_upper, 4),
        }


@dataclass
class WalkForwardResult:
    """Results from walk-forward validation."""

    n_folds: int = 0
    n_total_trades: int = 0  # Total trades in the dataset
    in_sample_metrics: list[PerformanceMetrics] = field(default_factory=list)
    out_of_sample_metrics: list[PerformanceMetrics] = field(default_factory=list)

    # Sample size adequacy
    insufficient_sample: bool = False
    sample_size_warning: str = ""

    # Aggregated OOS performance
    oos_total_trades: int = 0
    oos_total_pnl: float = 0.0
    oos_win_rate: float = 0.0
    oos_avg_pnl: float = 0.0
    oos_sharpe: float = 0.0

    # Consistency metrics
    oos_profitable_folds: int = 0
    oos_profitable_fold_pct: float = 0.0

    # Degradation from IS to OOS
    avg_win_rate_degradation: float = 0.0
    avg_pnl_degradation: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "n_folds": self.n_folds,
            "n_total_trades": self.n_total_trades,
            "insufficient_sample": bool(self.insufficient_sample),
            "sample_size_warning": self.sample_size_warning,
            "oos_total_trades": self.oos_total_trades,
            "oos_total_pnl": round(self.oos_total_pnl, 2),
            "oos_win_rate": round(self.oos_win_rate, 4),
            "oos_avg_pnl": round(self.oos_avg_pnl, 4),
            "oos_sharpe": round(self.oos_sharpe, 4),
            "oos_profitable_folds": self.oos_profitable_folds,
            "oos_profitable_fold_pct": round(self.oos_profitable_fold_pct, 4),
            "avg_win_rate_degradation": round(self.avg_win_rate_degradation, 4),
            "avg_pnl_degradation": round(self.avg_pnl_degradation, 4),
            "in_sample_summary": [m.to_dict() for m in self.in_sample_metrics],
            "out_of_sample_summary": [m.to_dict() for m in self.out_of_sample_metrics],
        }


def stratified_analysis(
    trades_df: pd.DataFrame,
    watchlist_df: pd.DataFrame | None = None,
    account_equity: float = 10000.0,
    min_sample_threshold: int = 30,
) -> StratifiedAnalysis:
    """
    Perform stratified analysis of trading performance.

    Args:
        trades_df: DataFrame with trade data (pnl, entry_ts, entry_reason, exit_reason, ticker).
        watchlist_df: Optional DataFrame with gap_pct per ticker/date.
        account_equity: Starting equity for metrics.
        min_sample_threshold: Minimum trades required for reliable statistics (default 30).
            Buckets with fewer trades are flagged as 'insufficient_sample' and
            their metrics (win_rate, expectancy, etc.) should not be used for conclusions.

    Returns:
        StratifiedAnalysis with metrics broken down by various dimensions.
        Metrics from buckets with N < min_sample_threshold are flagged.
    """
    result = StratifiedAnalysis()

    if trades_df.empty:
        return result

    trades = trades_df.copy()

    # Parse timestamps if needed
    if "entry_ts" in trades.columns:
        # Use utc=True to handle mixed timezones, then convert to US/Eastern
        trades["entry_ts_parsed"] = pd.to_datetime(trades["entry_ts"], utc=True)
        # Convert to Eastern time for hour/day analysis
        trades["entry_ts_parsed"] = trades["entry_ts_parsed"].dt.tz_convert("America/New_York")
        trades["entry_hour"] = trades["entry_ts_parsed"].dt.hour
        trades["entry_minute"] = trades["entry_ts_parsed"].dt.minute
        trades["day_of_week"] = trades["entry_ts_parsed"].dt.day_name()

    # Extract TTM state from entry_reason
    if "entry_reason" in trades.columns:
        trades["ttm_state"] = trades["entry_reason"].apply(_extract_ttm_state)

    # Merge gap data if available
    if watchlist_df is not None and not watchlist_df.empty:
        if "ticker" in trades.columns and "date" in trades.columns:
            trades = trades.merge(
                watchlist_df[["date", "ticker", "gap_pct"]],
                on=["date", "ticker"],
                how="left",
            )

    # 1. Analysis by gap bucket
    if "gap_pct" in trades.columns:
        trades["gap_bucket"] = pd.cut(
            trades["gap_pct"],
            bins=[0, 0.10, 0.20, 0.30, 0.50, 1.0, float("inf")],
            labels=["5-10%", "10-20%", "20-30%", "30-50%", "50-100%", "100%+"],
        )
        for bucket, group in trades.groupby("gap_bucket", observed=True):
            if len(group) > 0:
                result.by_gap_bucket[str(bucket)] = compute_metrics(
                    group, account_equity, min_sample_threshold=min_sample_threshold
                )

    # 2. Analysis by time of day
    if "entry_hour" in trades.columns:
        trades["time_bucket"] = trades.apply(_classify_time_of_day, axis=1)
        for time_bucket, group in trades.groupby("time_bucket"):
            if len(group) > 0:
                result.by_time_of_day[str(time_bucket)] = compute_metrics(
                    group, account_equity, min_sample_threshold=min_sample_threshold
                )

    # 3. Analysis by TTM state at entry
    if "ttm_state" in trades.columns:
        for state, group in trades.groupby("ttm_state"):
            if len(group) > 0 and state != "unknown":
                result.by_ttm_state[str(state)] = compute_metrics(
                    group, account_equity, min_sample_threshold=min_sample_threshold
                )

    # 4. Analysis by day of week
    if "day_of_week" in trades.columns:
        for dow, group in trades.groupby("day_of_week"):
            if len(group) > 0:
                result.by_day_of_week[str(dow)] = compute_metrics(
                    group, account_equity, min_sample_threshold=min_sample_threshold
                )

    # 5. Analysis by exit reason
    if "exit_reason" in trades.columns:
        for reason, group in trades.groupby("exit_reason"):
            if len(group) > 0:
                result.by_exit_reason[str(reason)] = compute_metrics(
                    group, account_equity, min_sample_threshold=min_sample_threshold
                )

    return result


def _extract_ttm_state(entry_reason: str) -> str:
    """Extract TTM state from entry reason string like 'pmh_breakout|ttm=weak_bull'."""
    if pd.isna(entry_reason):
        return "unknown"
    parts = str(entry_reason).split("|")
    for part in parts:
        if part.startswith("ttm="):
            return part[4:]
    return "unknown"


def _classify_time_of_day(row: pd.Series) -> str:
    """Classify entry time into market periods."""
    if "entry_hour" not in row or pd.isna(row["entry_hour"]):
        return "unknown"

    hour = int(row["entry_hour"])
    minute = int(row.get("entry_minute", 0))

    if hour < 9 or (hour == 9 and minute < 30):
        return "premarket"
    elif hour == 9 and minute < 45:
        return "open_15min"
    elif hour == 9:
        return "first_30min"
    elif hour == 10:
        return "10am_hour"
    elif hour == 11:
        return "11am_hour"
    elif hour < 15:
        return "midday"
    elif hour == 15:
        return "power_hour"
    else:
        return "after_hours"


def monte_carlo_simulation(
    trades_df: pd.DataFrame,
    n_simulations: int = 10000,
    account_equity: float = 10000.0,
    ruin_threshold_pct: float = 0.25,
    random_seed: int | None = None,
    min_sample_threshold: int = 30,
) -> MonteCarloResult:
    """
    Run Monte Carlo simulation by bootstrapping trade sequences.

    This helps assess:
    - Confidence intervals for total P&L and expectancy
    - Tail risk (worst-case scenarios)
    - Probability of ruin
    - Distribution of max drawdown

    Args:
        trades_df: DataFrame with pnl column.
        n_simulations: Number of bootstrap simulations.
        account_equity: Starting equity.
        ruin_threshold_pct: Drawdown percentage considered "ruin".
        random_seed: Optional seed for reproducibility.
        min_sample_threshold: Minimum trades required (default 30). Bootstrap
            results from fewer trades are statistically unreliable.

    Returns:
        MonteCarloResult with distribution statistics.
        Results from samples below threshold should be treated with caution.
    """
    result = MonteCarloResult(n_simulations=n_simulations)

    if trades_df.empty:
        return result

    pnl = trades_df["pnl"].astype(float).values
    n_trades = len(pnl)

    if n_trades == 0:
        return result

    result.n_trades = n_trades

    # Warn if sample size is too small for reliable bootstrap
    if n_trades < min_sample_threshold:
        result.insufficient_sample = True
        result.sample_size_warning = (
            f"Insufficient sample for Monte Carlo (N={n_trades} < {min_sample_threshold}). "
            "Bootstrap confidence intervals are unreliable."
        )

    result.original_total_pnl = float(pnl.sum())

    if random_seed is not None:
        np.random.seed(random_seed)

    # Run simulations
    final_pnls = np.zeros(n_simulations)
    max_drawdowns = np.zeros(n_simulations)
    expectancies = np.zeros(n_simulations)

    ruin_threshold = -account_equity * ruin_threshold_pct

    for i in range(n_simulations):
        # Bootstrap sample (sample with replacement)
        sample_idx = np.random.choice(n_trades, size=n_trades, replace=True)
        sample_pnl = pnl[sample_idx]

        # Compute final P&L
        final_pnls[i] = sample_pnl.sum()

        # Compute max drawdown for this sequence
        equity_curve = account_equity + np.cumsum(sample_pnl)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = equity_curve - running_max
        max_drawdowns[i] = drawdown.min()

        # Compute expectancy
        wins = sample_pnl[sample_pnl > 0]
        losses = sample_pnl[sample_pnl < 0]
        win_rate = len(wins) / n_trades if n_trades > 0 else 0
        loss_rate = len(losses) / n_trades if n_trades > 0 else 0
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        expectancies[i] = (win_rate * avg_win) + (loss_rate * avg_loss)

    # P&L distribution
    result.mean_final_pnl = float(np.mean(final_pnls))
    result.median_final_pnl = float(np.median(final_pnls))
    result.std_final_pnl = float(np.std(final_pnls))
    result.pnl_5th_percentile = float(np.percentile(final_pnls, 5))
    result.pnl_25th_percentile = float(np.percentile(final_pnls, 25))
    result.pnl_75th_percentile = float(np.percentile(final_pnls, 75))
    result.pnl_95th_percentile = float(np.percentile(final_pnls, 95))

    # Drawdown distribution
    result.mean_max_drawdown = float(np.mean(max_drawdowns))
    result.median_max_drawdown = float(np.median(max_drawdowns))
    result.max_drawdown_95th_percentile = float(np.percentile(max_drawdowns, 5))  # 5th percentile is worst

    # Risk metrics
    result.probability_of_profit = float((final_pnls > 0).mean())
    result.probability_of_ruin = float((max_drawdowns < ruin_threshold).mean())

    # VaR and CVaR (Expected Shortfall)
    result.var_95 = float(np.percentile(final_pnls, 5))
    below_var = final_pnls[final_pnls <= result.var_95]
    result.cvar_95 = float(below_var.mean()) if len(below_var) > 0 else result.var_95

    # Confidence interval for expectancy (95% CI)
    result.expectancy_ci_lower = float(np.percentile(expectancies, 2.5))
    result.expectancy_ci_upper = float(np.percentile(expectancies, 97.5))

    return result


def walk_forward_validation(
    trades_df: pd.DataFrame,
    n_folds: int = 5,
    train_pct: float = 0.7,
    account_equity: float = 10000.0,
    min_sample_threshold: int = 30,
) -> WalkForwardResult:
    """
    Perform walk-forward validation to test out-of-sample performance.

    Splits trades chronologically into train/test folds and computes
    metrics for each to assess strategy robustness.

    Args:
        trades_df: DataFrame with trade data, must have 'entry_ts' or 'date' for ordering.
        n_folds: Number of walk-forward folds.
        train_pct: Percentage of each fold used for training.
        account_equity: Starting equity for metrics.
        min_sample_threshold: Minimum trades for meaningful walk-forward (default 30).
            With fewer trades, results are flagged as unreliable.

    Returns:
        WalkForwardResult with in-sample and out-of-sample metrics.
    """
    result = WalkForwardResult(n_folds=n_folds)

    if trades_df.empty:
        result.insufficient_sample = True
        result.sample_size_warning = "No trades for walk-forward validation"
        return result

    trades = trades_df.copy()

    # Sort by entry time
    if "entry_ts" in trades.columns:
        trades["sort_key"] = pd.to_datetime(trades["entry_ts"])
    elif "date" in trades.columns:
        trades["sort_key"] = pd.to_datetime(trades["date"])
    else:
        # Fall back to index order
        trades["sort_key"] = range(len(trades))

    trades = trades.sort_values("sort_key").reset_index(drop=True)
    n_trades = len(trades)
    result.n_total_trades = n_trades

    # Check if we have enough trades
    if n_trades < min_sample_threshold:
        result.insufficient_sample = True
        result.sample_size_warning = (
            f"Insufficient sample for walk-forward (N={n_trades} < {min_sample_threshold}). "
            "Results are statistically unreliable."
        )

    if n_trades < n_folds * 2:
        # Not enough trades for meaningful walk-forward
        if not result.insufficient_sample:
            result.insufficient_sample = True
            result.sample_size_warning = (
                f"Too few trades for {n_folds}-fold walk-forward (N={n_trades} < {n_folds * 2})"
            )
        return result

    # Calculate fold size
    fold_size = n_trades // n_folds

    is_metrics_list: list[PerformanceMetrics] = []
    oos_metrics_list: list[PerformanceMetrics] = []
    oos_trades_list: list[pd.DataFrame] = []

    for fold_idx in range(n_folds):
        # Define fold boundaries
        fold_start = fold_idx * fold_size
        fold_end = (fold_idx + 1) * fold_size if fold_idx < n_folds - 1 else n_trades

        fold_trades = trades.iloc[fold_start:fold_end]
        fold_n = len(fold_trades)

        if fold_n < 4:
            continue

        # Split into train/test
        train_n = int(fold_n * train_pct)
        train_trades = fold_trades.iloc[:train_n]
        test_trades = fold_trades.iloc[train_n:]

        if len(train_trades) < 2 or len(test_trades) < 1:
            continue

        # Compute metrics
        is_metrics = compute_metrics(train_trades, account_equity)
        oos_metrics = compute_metrics(test_trades, account_equity)

        is_metrics_list.append(is_metrics)
        oos_metrics_list.append(oos_metrics)
        oos_trades_list.append(test_trades)

    result.in_sample_metrics = is_metrics_list
    result.out_of_sample_metrics = oos_metrics_list

    # Aggregate OOS results
    if oos_trades_list:
        all_oos = pd.concat(oos_trades_list, ignore_index=True)
        oos_agg = compute_metrics(all_oos, account_equity)

        result.oos_total_trades = oos_agg.total_trades
        result.oos_total_pnl = oos_agg.total_pnl
        result.oos_win_rate = oos_agg.win_rate
        result.oos_avg_pnl = oos_agg.avg_pnl
        result.oos_sharpe = oos_agg.sharpe_ratio

    # Count profitable OOS folds
    result.oos_profitable_folds = sum(1 for m in oos_metrics_list if m.total_pnl > 0)
    result.oos_profitable_fold_pct = (
        result.oos_profitable_folds / len(oos_metrics_list)
        if oos_metrics_list else 0.0
    )

    # Compute degradation metrics
    if is_metrics_list and oos_metrics_list:
        win_rate_diffs = []
        pnl_diffs = []

        for is_m, oos_m in zip(is_metrics_list, oos_metrics_list):
            win_rate_diffs.append(is_m.win_rate - oos_m.win_rate)
            if is_m.avg_pnl != 0:
                pnl_diffs.append((is_m.avg_pnl - oos_m.avg_pnl) / abs(is_m.avg_pnl))

        result.avg_win_rate_degradation = float(np.mean(win_rate_diffs)) if win_rate_diffs else 0.0
        result.avg_pnl_degradation = float(np.mean(pnl_diffs)) if pnl_diffs else 0.0

    return result


@dataclass
class NegativeControlResult:
    """
    Results from negative control tests for statistical significance.

    This replaces the invalid "permutation test" that shuffled P&L order.
    The block bootstrap method resamples entire trading days to create a
    valid null distribution that tests H0: E[daily P&L] = 0.
    """

    method: str = "block_bootstrap"  # Method used for null generation
    n_bootstrap: int = 0
    n_days: int = 0
    n_trades: int = 0

    # Original observed values
    observed_mean_daily_pnl: float = 0.0
    observed_total_pnl: float = 0.0
    observed_sharpe: float = 0.0

    # Sample size adequacy
    insufficient_sample: bool = False
    sample_size_warning: str = ""

    # Null distribution (centered at zero via mean-subtraction)
    null_mean: float = 0.0  # Should be ~0 by construction
    null_std: float = 0.0  # Standard error of the mean
    null_5th_percentile: float = 0.0
    null_95th_percentile: float = 0.0

    # Significance testing (two-sided test of H0: mean = 0)
    t_statistic: float = 0.0
    p_value: float = 1.0
    is_significant_5pct: bool = False
    is_significant_1pct: bool = False

    # Bootstrap confidence interval for mean daily P&L
    ci_lower_95: float = 0.0
    ci_upper_95: float = 0.0

    # Interpretation
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "method": self.method,
            "n_bootstrap": self.n_bootstrap,
            "n_days": self.n_days,
            "n_trades": self.n_trades,
            "observed_mean_daily_pnl": round(self.observed_mean_daily_pnl, 4),
            "observed_total_pnl": round(self.observed_total_pnl, 2),
            "observed_sharpe": round(self.observed_sharpe, 4),
            "insufficient_sample": bool(self.insufficient_sample),
            "sample_size_warning": self.sample_size_warning,
            "null_mean": round(self.null_mean, 4),
            "null_std": round(self.null_std, 4),
            "null_5th_percentile": round(self.null_5th_percentile, 4),
            "null_95th_percentile": round(self.null_95th_percentile, 4),
            "t_statistic": round(self.t_statistic, 4),
            "p_value": round(self.p_value, 6) if self.p_value >= 1e-6 else f"{self.p_value:.2e}",
            "p_value_numeric": self.p_value,
            "is_significant_5pct": bool(self.is_significant_5pct),
            "is_significant_1pct": bool(self.is_significant_1pct),
            "ci_lower_95": round(self.ci_lower_95, 4),
            "ci_upper_95": round(self.ci_upper_95, 4),
            "interpretation": self.interpretation,
        }


def block_bootstrap_test(
    trades_df: pd.DataFrame,
    n_bootstrap: int = 10000,
    random_seed: int | None = None,
    min_days_threshold: int = 20,
    all_trading_days: list[str] | None = None,
) -> NegativeControlResult:
    """
    Perform block bootstrap HYPOTHESIS TEST on mean daily P&L.

    NOTE: This is an INFERENCE METHOD testing H0: E[daily P&L] = 0.
    It is NOT a leakage-detecting negative control (which would break
    signal→return structure, e.g., by randomizing entry times).

    The test works by:
    1. Computing daily P&L (including 0-trade days if all_trading_days provided)
    2. Centering daily P&L at zero (subtracting observed mean)
    3. Resampling days with replacement to generate null distribution
    4. Computing p-value as proportion of |bootstrap_mean| >= |observed_mean|

    Args:
        trades_df: DataFrame with 'pnl' and 'date' columns.
        n_bootstrap: Number of bootstrap samples.
        random_seed: Optional seed for reproducibility.
        min_days_threshold: Minimum trading days required (default 20).
        all_trading_days: Optional list of all trading days (YYYY-MM-DD strings).
            If provided, 0-trade days are included with P&L=0 for consistency
            with compute_metrics().

    Returns:
        NegativeControlResult with null distribution and p-values.
    """
    result = NegativeControlResult(method="block_bootstrap", n_bootstrap=n_bootstrap)

    if trades_df.empty and (all_trading_days is None or len(all_trading_days) == 0):
        result.insufficient_sample = True
        result.sample_size_warning = "No trades and no trading days for bootstrap test"
        return result

    # Ensure we have date column (unless using all_trading_days with empty trades)
    if not trades_df.empty and "date" not in trades_df.columns:
        result.insufficient_sample = True
        result.sample_size_warning = "No 'date' column - cannot perform day-level bootstrap"
        return result

    result.n_trades = len(trades_df)

    # Compute daily P&L INCLUDING 0-trade days for consistency with compute_metrics()
    if all_trading_days is not None and len(all_trading_days) > 0:
        # Build complete daily P&L series including 0-trade days
        all_days_index = pd.Index(all_trading_days, name="date")
        daily_pnl_series = pd.Series(0.0, index=all_days_index)

        if not trades_df.empty:
            daily_pnl_with_trades = trades_df.groupby("date")["pnl"].sum()
            for dt in daily_pnl_with_trades.index:
                if dt in daily_pnl_series.index:
                    daily_pnl_series[dt] = daily_pnl_with_trades[dt]

        daily_pnl = daily_pnl_series.values
    else:
        # Fallback: use only days with trades (backward compatible but inconsistent)
        daily_pnl = trades_df.groupby("date")["pnl"].sum().values

    n_days = len(daily_pnl)
    result.n_days = n_days

    if n_days < min_days_threshold:
        result.insufficient_sample = True
        result.sample_size_warning = (
            f"Insufficient trading days for bootstrap (N={n_days} < {min_days_threshold}). "
            "Results may be unreliable."
        )

    if n_days < 5:
        result.sample_size_warning = "Too few trading days for meaningful bootstrap test"
        return result

    # Compute observed statistics
    observed_mean = float(np.mean(daily_pnl))
    observed_std = float(np.std(daily_pnl, ddof=1))
    result.observed_mean_daily_pnl = observed_mean
    result.observed_total_pnl = float(np.sum(daily_pnl))

    # Compute observed Sharpe (annualized)
    if observed_std > 0:
        result.observed_sharpe = observed_mean / observed_std * np.sqrt(252)
    else:
        result.observed_sharpe = 0.0

    if random_seed is not None:
        np.random.seed(random_seed)

    # CENTER the daily P&L at zero for null hypothesis
    # H0: E[daily P&L] = 0 means we subtract the observed mean
    centered_daily_pnl = daily_pnl - observed_mean

    # Generate bootstrap distribution of the mean under H0
    bootstrap_means = np.zeros(n_bootstrap)

    for i in range(n_bootstrap):
        # Resample days WITH replacement
        sample_idx = np.random.choice(n_days, size=n_days, replace=True)
        bootstrap_sample = centered_daily_pnl[sample_idx]
        bootstrap_means[i] = np.mean(bootstrap_sample)

    # Null distribution statistics
    result.null_mean = float(np.mean(bootstrap_means))  # Should be ~0
    result.null_std = float(np.std(bootstrap_means))  # Standard error of the mean
    result.null_5th_percentile = float(np.percentile(bootstrap_means, 5))
    result.null_95th_percentile = float(np.percentile(bootstrap_means, 95))

    # Two-sided p-value: P(|bootstrap_mean| >= |observed_mean|)
    # Since bootstrap is centered at 0, we compare absolute values
    extreme_count = np.sum(np.abs(bootstrap_means) >= np.abs(observed_mean))
    result.p_value = (extreme_count + 1) / (n_bootstrap + 1)

    # T-statistic (observed mean / standard error)
    if result.null_std > 0:
        result.t_statistic = observed_mean / result.null_std
    else:
        result.t_statistic = 0.0

    # Significance flags
    result.is_significant_5pct = result.p_value < 0.05
    result.is_significant_1pct = result.p_value < 0.01

    # Bootstrap confidence interval for mean (using UN-centered bootstrap)
    # This tells us the range of plausible mean values
    uncentered_bootstrap_means = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        sample_idx = np.random.choice(n_days, size=n_days, replace=True)
        uncentered_bootstrap_means[i] = np.mean(daily_pnl[sample_idx])

    result.ci_lower_95 = float(np.percentile(uncentered_bootstrap_means, 2.5))
    result.ci_upper_95 = float(np.percentile(uncentered_bootstrap_means, 97.5))

    # Generate interpretation
    result.interpretation = _interpret_bootstrap_result(result)

    return result


def _interpret_bootstrap_result(result: NegativeControlResult) -> str:
    """Generate human-readable interpretation of bootstrap test results."""
    if result.insufficient_sample:
        return "Insufficient sample size for reliable conclusions."

    direction = "negative" if result.observed_mean_daily_pnl < 0 else "positive"

    if result.is_significant_1pct:
        significance = "highly significant (p < 0.01)"
    elif result.is_significant_5pct:
        significance = "significant (p < 0.05)"
    else:
        significance = "not statistically significant (p >= 0.05)"

    # Check if CI excludes zero
    ci_excludes_zero = (result.ci_lower_95 > 0) or (result.ci_upper_95 < 0)

    if result.is_significant_5pct:
        conclusion = (
            f"The strategy has a {significance} {direction} edge. "
            f"Mean daily P&L = ${result.observed_mean_daily_pnl:.2f} "
            f"(95% CI: ${result.ci_lower_95:.2f} to ${result.ci_upper_95:.2f}). "
        )
        if ci_excludes_zero:
            conclusion += "The confidence interval excludes zero, confirming the edge."
    else:
        conclusion = (
            f"The strategy's performance is {significance}. "
            f"Mean daily P&L = ${result.observed_mean_daily_pnl:.2f} "
            f"(95% CI: ${result.ci_lower_95:.2f} to ${result.ci_upper_95:.2f}). "
            "The observed performance could plausibly have occurred by chance."
        )

    return conclusion


# Keep old function name as alias for backwards compatibility, but mark deprecated
def permutation_test(
    trades_df: pd.DataFrame,
    n_permutations: int = 10000,
    metric: str = "sharpe",
    random_seed: int | None = None,
    min_sample_threshold: int = 30,
) -> NegativeControlResult:
    """
    DEPRECATED: Use block_bootstrap_test() instead.

    The original permutation test was statistically invalid because it shuffled
    trade P&L order and computed order-invariant metrics (total_pnl, sharpe, etc.),
    creating a degenerate null distribution.

    This function now redirects to block_bootstrap_test() which properly tests
    H0: E[daily P&L] = 0 using day-level block bootstrap.
    """
    import warnings
    warnings.warn(
        "permutation_test() is deprecated and was statistically invalid. "
        "Use block_bootstrap_test() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return block_bootstrap_test(
        trades_df,
        n_bootstrap=n_permutations,
        random_seed=random_seed,
        min_days_threshold=min_sample_threshold,
    )


def compute_regime_analysis(
    trades_df: pd.DataFrame,
    market_data: pd.DataFrame | None = None,
    account_equity: float = 10000.0,
    min_sample_threshold: int = 30,
) -> dict[str, PerformanceMetrics]:
    """
    Analyze performance across different market regimes.

    If market_data is provided (with columns like 'spy_return'), classify days
    into bull/bear/sideways regimes and compute metrics for each.

    Args:
        trades_df: DataFrame with trade data.
        market_data: Optional DataFrame with market regime indicators.
        account_equity: Starting equity.
        min_sample_threshold: Minimum trades for reliable statistics (default 30).

    Returns:
        Dictionary mapping regime names to PerformanceMetrics.
        Metrics from regimes with N < min_sample_threshold are flagged.
    """
    if trades_df.empty:
        return {}

    # If no market data, just return overall metrics
    if market_data is None or market_data.empty:
        return {"all": compute_metrics(trades_df, account_equity, min_sample_threshold=min_sample_threshold)}

    trades = trades_df.copy()

    # Merge market data
    if "date" in trades.columns and "date" in market_data.columns:
        trades = trades.merge(market_data, on="date", how="left")
    else:
        return {"all": compute_metrics(trades_df, account_equity, min_sample_threshold=min_sample_threshold)}

    results: dict[str, PerformanceMetrics] = {}

    # Classify by SPY return if available
    if "spy_return" in trades.columns:
        trades["regime"] = trades["spy_return"].apply(
            lambda x: "bull" if x > 0.005 else ("bear" if x < -0.005 else "sideways")
            if pd.notna(x) else "unknown"
        )

        for regime, group in trades.groupby("regime"):
            if len(group) > 0 and regime != "unknown":
                results[str(regime)] = compute_metrics(
                    group, account_equity, min_sample_threshold=min_sample_threshold
                )

    return results


# =============================================================================
# HEURISTIC STRESS TESTS (NOT true negative controls for leakage detection)
# =============================================================================
#
# IMPORTANT LIMITATION: These tests operate on already-realized P&L values.
# They do NOT resimulate the backtest with modified entry times using price data.
# Therefore, they CANNOT reliably detect lookahead bias.
#
# For true lookahead detection, verify:
# 1. signal_ts < entry_ts for all trades (tested elsewhere)
# 2. Indicators use only past data (code review)
# 3. Watchlist uses only data available at selection time (code review)
#
# These stress tests are kept for informational purposes but their outputs
# should NOT be interpreted as evidence for or against lookahead bias.
# =============================================================================

@dataclass
class StressTestResult:
    """Result of a heuristic stress test.

    IMPORTANT: These are NOT true negative controls for leakage detection.
    They operate on realized P&L and cannot detect lookahead bias.
    """
    method: str = ""
    n_simulations: int = 0
    n_trades: int = 0

    # Observed (original) statistics
    observed_mean_pnl: float = 0.0
    observed_total_pnl: float = 0.0
    observed_win_rate: float = 0.0

    # Perturbed distribution statistics
    perturbed_mean_pnl: float = 0.0
    perturbed_std_pnl: float = 0.0
    perturbed_total_pnl_mean: float = 0.0
    perturbed_win_rate_mean: float = 0.0

    # Interpretation
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "method": self.method,
            "n_simulations": self.n_simulations,
            "n_trades": self.n_trades,
            "observed_mean_pnl": round(self.observed_mean_pnl, 4),
            "observed_total_pnl": round(self.observed_total_pnl, 2),
            "observed_win_rate": round(self.observed_win_rate, 4),
            "perturbed_mean_pnl": round(self.perturbed_mean_pnl, 4),
            "perturbed_std_pnl": round(self.perturbed_std_pnl, 4),
            "perturbed_total_pnl_mean": round(self.perturbed_total_pnl_mean, 2),
            "perturbed_win_rate_mean": round(self.perturbed_win_rate_mean, 4),
            "interpretation": self.interpretation,
        }


# Keep old name as alias for backwards compatibility
LeakageControlResult = StressTestResult


def time_shift_negative_control(
    trades_df: pd.DataFrame,
    shift_minutes: int = 5,
    n_simulations: int = 1000,
    random_seed: int | None = None,
) -> StressTestResult:
    """
    HEURISTIC stress test: perturb P&L to simulate delayed entries.

    IMPORTANT LIMITATION: This does NOT actually resimulate with shifted
    entry times using price data. It randomly drops trades and adds noise
    to existing P&L values. This CANNOT detect lookahead bias.

    For actual lookahead detection, verify signal_ts < entry_ts for all trades.

    Args:
        trades_df: DataFrame with 'pnl' column.
        shift_minutes: Conceptual shift (affects drop probability).
        n_simulations: Number of simulations.
        random_seed: Optional seed for reproducibility.

    Returns:
        StressTestResult with perturbed distribution statistics.
    """
    result = StressTestResult(
        method=f"time_shift_heuristic_{shift_minutes}min",
        n_simulations=n_simulations,
    )

    if trades_df.empty or "pnl" not in trades_df.columns:
        result.interpretation = "No trades to analyze"
        return result

    result.n_trades = len(trades_df)
    pnl = trades_df["pnl"].astype(float)

    # Observed statistics
    result.observed_mean_pnl = float(pnl.mean())
    result.observed_total_pnl = float(pnl.sum())
    result.observed_win_rate = float((pnl > 0).mean())

    if random_seed is not None:
        np.random.seed(random_seed)

    # Heuristic: randomly drop some trades and add noise
    # This is NOT a true negative control - just a stress test
    perturbed_means: list[float] = []
    perturbed_totals: list[float] = []
    perturbed_win_rates: list[float] = []

    for _ in range(n_simulations):
        drop_prob = min(0.5, shift_minutes / 60.0)
        keep_mask = np.random.random(len(pnl)) > drop_prob

        if keep_mask.sum() > 0:
            sample_pnl = pnl[keep_mask]
            noise = np.random.normal(0, abs(result.observed_mean_pnl) * 0.5, len(sample_pnl))
            adjusted_pnl = sample_pnl + noise

            perturbed_means.append(float(adjusted_pnl.mean()))
            perturbed_totals.append(float(adjusted_pnl.sum()))
            perturbed_win_rates.append(float((adjusted_pnl > 0).mean()))
        else:
            perturbed_means.append(0.0)
            perturbed_totals.append(0.0)
            perturbed_win_rates.append(0.0)

    # Compute statistics
    result.perturbed_mean_pnl = float(np.mean(perturbed_means))
    result.perturbed_std_pnl = float(np.std(perturbed_means))
    result.perturbed_total_pnl_mean = float(np.mean(perturbed_totals))
    result.perturbed_win_rate_mean = float(np.mean(perturbed_win_rates))

    # Interpretation - be honest about limitations
    result.interpretation = (
        f"Heuristic perturbation test (NOT a true leakage control). "
        f"Observed mean: ${result.observed_mean_pnl:.2f}, "
        f"Perturbed mean: ${result.perturbed_mean_pnl:.2f} (std: ${result.perturbed_std_pnl:.2f}). "
        f"For lookahead detection, verify signal_ts < entry_ts for all trades."
    )

    return result


def shuffle_dates_negative_control(
    trades_df: pd.DataFrame,
    n_simulations: int = 1000,
    random_seed: int | None = None,
) -> StressTestResult:
    """
    HEURISTIC stress test: permute P&L values.

    IMPORTANT LIMITATION: Permuting P&L values does NOT break the signal→return
    relationship because it operates on realized outcomes, not on price data.
    The mean is permutation-invariant, so this test has near-zero variance
    and CANNOT detect lookahead bias.

    Args:
        trades_df: DataFrame with 'pnl' column.
        n_simulations: Number of simulations.
        random_seed: Optional seed for reproducibility.

    Returns:
        StressTestResult with perturbed distribution statistics.
    """
    result = StressTestResult(
        method="shuffle_heuristic",
        n_simulations=n_simulations,
    )

    if trades_df.empty or "pnl" not in trades_df.columns:
        result.interpretation = "No trades to analyze"
        return result

    result.n_trades = len(trades_df)
    pnl = trades_df["pnl"].astype(float).values

    # Observed statistics
    result.observed_mean_pnl = float(np.mean(pnl))
    result.observed_total_pnl = float(np.sum(pnl))
    result.observed_win_rate = float((pnl > 0).mean())

    if random_seed is not None:
        np.random.seed(random_seed)

    # Shuffle P&L values (permutation-invariant for mean, so std ≈ 0)
    perturbed_means: list[float] = []
    perturbed_totals: list[float] = []
    perturbed_win_rates: list[float] = []

    for _ in range(n_simulations):
        shuffled_pnl = np.random.permutation(pnl)
        perturbed_means.append(float(np.mean(shuffled_pnl)))
        perturbed_totals.append(float(np.sum(shuffled_pnl)))
        perturbed_win_rates.append(float((shuffled_pnl > 0).mean()))

    # Compute statistics
    result.perturbed_mean_pnl = float(np.mean(perturbed_means))
    result.perturbed_std_pnl = float(np.std(perturbed_means))
    result.perturbed_total_pnl_mean = float(np.mean(perturbed_totals))
    result.perturbed_win_rate_mean = float(np.mean(perturbed_win_rates))

    # Be honest about the limitations
    result.interpretation = (
        f"Shuffle heuristic (NOT a true leakage control). "
        f"Mean is permutation-invariant so std≈0 (got ${result.perturbed_std_pnl:.4f}). "
        f"This test cannot detect lookahead bias. "
        f"For lookahead detection, verify signal_ts < entry_ts for all trades."
    )

    return result


# =============================================================================
# P&L RECONCILIATION
# =============================================================================


@dataclass
class ReconciliationResult:
    """Result of reconciling trades.csv P&L against fills.csv reconstructed P&L."""

    is_consistent: bool = True
    total_trades: int = 0
    trades_with_discrepancy: int = 0
    max_discrepancy: float = 0.0
    total_discrepancy: float = 0.0

    # Trade P&L totals
    trades_total_pnl: float = 0.0
    fills_reconstructed_pnl: float = 0.0
    difference: float = 0.0

    # Details for debugging
    discrepancies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_consistent": self.is_consistent,
            "total_trades": self.total_trades,
            "trades_with_discrepancy": self.trades_with_discrepancy,
            "max_discrepancy": self.max_discrepancy,
            "total_discrepancy": self.total_discrepancy,
            "trades_total_pnl": self.trades_total_pnl,
            "fills_reconstructed_pnl": self.fills_reconstructed_pnl,
            "difference": self.difference,
            "discrepancies": self.discrepancies[:10] if self.discrepancies else [],  # Limit to first 10
        }


def reconcile_trades_and_fills(
    trades_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    tolerance: float = 0.01,  # $0.01 tolerance for floating point
    fees_per_trade: float = 0.0,
) -> ReconciliationResult:
    """
    Reconcile trade P&L against fill-reconstructed P&L.

    This verifies that the P&L recorded in trades.csv matches what would be
    computed from the fills in fills.csv. This catches accounting bugs like:
    - Missing partial scale-out P&L in trade records
    - Double-counting fees
    - Incorrect quantity tracking

    Algorithm:
    1. Group fills by (date, ticker)
    2. For each group, match BUY and SELL fills
    3. Compute P&L as: sum(sell_qty * sell_px) - sum(buy_qty * buy_px) - fees
    4. Compare against trade P&L

    Args:
        trades_df: DataFrame with columns ['date', 'ticker', 'pnl']
        fills_df: DataFrame with columns ['date', 'ticker', 'side', 'qty', 'price']
        tolerance: Maximum acceptable discrepancy in dollars
        fees_per_trade: Fees per round-trip (applied once per complete trade)

    Returns:
        ReconciliationResult with consistency verdict and discrepancies
    """
    result = ReconciliationResult()

    if trades_df.empty:
        result.is_consistent = True
        return result

    if fills_df.empty:
        result.is_consistent = False
        result.discrepancies.append({
            "error": "No fills provided but trades exist",
            "trades_count": len(trades_df),
        })
        return result

    # Ensure required columns exist
    for col in ["date", "ticker", "pnl"]:
        if col not in trades_df.columns:
            raise ValueError(f"trades_df missing required column: {col}")

    for col in ["date", "ticker", "side", "qty", "price"]:
        if col not in fills_df.columns:
            raise ValueError(f"fills_df missing required column: {col}")

    # Convert to standard types
    trades = trades_df.copy()
    fills = fills_df.copy()

    trades["date"] = trades["date"].astype(str)
    trades["ticker"] = trades["ticker"].astype(str)
    fills["date"] = fills["date"].astype(str)
    fills["ticker"] = fills["ticker"].astype(str)
    fills["qty"] = fills["qty"].astype(float)
    fills["price"] = fills["price"].astype(float)
    fills["side"] = fills["side"].astype(str)

    # Group fills by (date, ticker)
    fill_groups = fills.groupby(["date", "ticker"])

    # Group trades by (date, ticker) - may have multiple trades per day per ticker
    # We need to match trade sequences with fill sequences

    result.total_trades = len(trades)
    result.trades_total_pnl = float(trades["pnl"].sum())

    # Reconstruct P&L from fills
    reconstructed_pnl_total = 0.0

    for (date, ticker), group in fill_groups:
        buys = group[group["side"] == "BUY"]
        sells = group[group["side"] == "SELL"]

        # Total cost of buys
        total_buy_cost = (buys["qty"] * buys["price"]).sum()
        total_buy_qty = buys["qty"].sum()

        # Total proceeds from sells
        total_sell_proceeds = (sells["qty"] * sells["price"]).sum()
        total_sell_qty = sells["qty"].sum()

        # Verify quantities match (position should be flat at end of day)
        if abs(total_buy_qty - total_sell_qty) > 0.001:
            result.discrepancies.append({
                "date": date,
                "ticker": ticker,
                "error": "Quantity mismatch",
                "buy_qty": float(total_buy_qty),
                "sell_qty": float(total_sell_qty),
            })

        # Count complete trades (each BUY that starts a position = 1 trade)
        # For simplicity, count trades where entry_ts changes
        n_trades_in_group = len(buys)  # Each BUY starts a new trade

        # Reconstructed P&L = proceeds - cost - fees
        # Fees applied once per trade (round-trip)
        group_pnl = total_sell_proceeds - total_buy_cost - (fees_per_trade * n_trades_in_group)
        reconstructed_pnl_total += group_pnl

        # Find matching trades in trades_df
        matching_trades = trades[(trades["date"] == date) & (trades["ticker"] == ticker)]
        trades_pnl = matching_trades["pnl"].sum()

        # Check for discrepancy
        discrepancy = abs(group_pnl - trades_pnl)
        if discrepancy > tolerance:
            result.trades_with_discrepancy += 1
            result.total_discrepancy += discrepancy
            result.max_discrepancy = max(result.max_discrepancy, discrepancy)
            result.discrepancies.append({
                "date": date,
                "ticker": ticker,
                "fills_reconstructed_pnl": float(group_pnl),
                "trades_pnl": float(trades_pnl),
                "discrepancy": float(discrepancy),
                "buys": len(buys),
                "sells": len(sells),
            })

    result.fills_reconstructed_pnl = reconstructed_pnl_total
    result.difference = abs(result.trades_total_pnl - result.fills_reconstructed_pnl)

    # Check overall consistency
    result.is_consistent = (
        result.trades_with_discrepancy == 0 and
        result.difference <= tolerance * result.total_trades
    )

    return result


# =============================================================================
# LEAKAGE AUDIT
# =============================================================================

@dataclass
class LeakageAuditResult:
    """
    Results from leakage audit verifying signal->entry causality.

    WHAT THIS CHECKS:
    - signal_ts < entry_ts: Signal timestamp strictly precedes entry timestamp
    - signal_ts != entry_ts: Signal and entry are not at the same timestamp

    WHAT THIS DOES NOT CHECK:
    - Bar-level causality (requires knowing bar frequency)
    - Feature computation lookahead (requires code review)
    - Watchlist selection lookahead (requires code review)

    NOTE: For minute-bar backtests, signal_equals_entry effectively catches
    same-bar fills since both would round to the same minute.
    """
    total_trades: int = 0
    trades_with_signal_ts: int = 0
    trades_with_entry_ts: int = 0

    # Violation counts (must be zero for valid backtest)
    signal_after_entry_violations: int = 0      # signal_ts > entry_ts
    signal_equals_entry_violations: int = 0     # signal_ts == entry_ts

    # Details of violations (if any)
    violation_details: list[dict[str, Any]] = field(default_factory=list)

    # Overall pass/fail
    is_valid: bool = False
    audit_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_trades": self.total_trades,
            "trades_with_signal_ts": self.trades_with_signal_ts,
            "trades_with_entry_ts": self.trades_with_entry_ts,
            "signal_after_entry_violations": self.signal_after_entry_violations,
            "signal_equals_entry_violations": self.signal_equals_entry_violations,
            "total_violations": (
                self.signal_after_entry_violations +
                self.signal_equals_entry_violations
            ),
            "is_valid": self.is_valid,
            "audit_message": self.audit_message,
            "violation_details": self.violation_details[:10],  # Limit to first 10
        }


def leakage_audit(trades_df: pd.DataFrame) -> LeakageAuditResult:
    """
    Audit trades for signal->entry causality violations.

    Checks that for ALL trades with both signal_ts and entry_ts:
    1. signal_ts < entry_ts (signal must strictly precede entry)
    2. signal_ts != entry_ts (no same-timestamp signals and entries)

    NOTE: This checks timestamp ordering only. It does NOT verify:
    - Bar-level causality (requires knowing bar frequency)
    - Feature computation lookahead (requires code review)
    - Watchlist selection lookahead (requires code review)

    For minute-bar backtests, signal_equals_entry effectively catches
    same-bar fills since both timestamps round to the same minute.

    Args:
        trades_df: DataFrame with 'signal_ts' and 'entry_ts' columns.

    Returns:
        LeakageAuditResult with violation counts and pass/fail status.
    """
    result = LeakageAuditResult()
    result.total_trades = len(trades_df)

    if trades_df.empty:
        result.is_valid = True
        result.audit_message = "No trades to audit"
        return result

    # Check for required columns
    has_signal_ts = "signal_ts" in trades_df.columns
    has_entry_ts = "entry_ts" in trades_df.columns

    if not has_signal_ts or not has_entry_ts:
        result.is_valid = False
        result.audit_message = f"Missing required columns: signal_ts={has_signal_ts}, entry_ts={has_entry_ts}"
        return result

    # Parse timestamps
    for idx, row in trades_df.iterrows():
        signal_ts = row.get("signal_ts")
        entry_ts = row.get("entry_ts")

        if pd.notna(signal_ts):
            result.trades_with_signal_ts += 1
        if pd.notna(entry_ts):
            result.trades_with_entry_ts += 1

        if pd.isna(signal_ts) or pd.isna(entry_ts):
            continue

        # Parse timestamps
        try:
            if isinstance(signal_ts, str):
                signal_dt = pd.Timestamp(signal_ts)
            else:
                signal_dt = pd.Timestamp(signal_ts)

            if isinstance(entry_ts, str):
                entry_dt = pd.Timestamp(entry_ts)
            else:
                entry_dt = pd.Timestamp(entry_ts)
        except Exception:
            continue

        # Check for violations
        if signal_dt > entry_dt:
            result.signal_after_entry_violations += 1
            result.violation_details.append({
                "type": "signal_after_entry",
                "date": row.get("date"),
                "ticker": row.get("ticker"),
                "signal_ts": str(signal_ts),
                "entry_ts": str(entry_ts),
            })
        elif signal_dt == entry_dt:
            result.signal_equals_entry_violations += 1
            result.violation_details.append({
                "type": "signal_equals_entry",
                "date": row.get("date"),
                "ticker": row.get("ticker"),
                "signal_ts": str(signal_ts),
                "entry_ts": str(entry_ts),
            })

    # Determine overall validity
    total_violations = (
        result.signal_after_entry_violations +
        result.signal_equals_entry_violations
    )

    result.is_valid = total_violations == 0

    if result.is_valid:
        result.audit_message = (
            f"PASS: All {result.trades_with_signal_ts} trades have signal_ts < entry_ts. "
            "Signal->entry causality verified."
        )
    else:
        result.audit_message = (
            f"FAIL: {total_violations} causality violations detected. "
            f"signal_after_entry={result.signal_after_entry_violations}, "
            f"signal_equals_entry={result.signal_equals_entry_violations}. "
            "This indicates potential lookahead bias in signal generation."
        )

    return result


# =============================================================================
# DAILY SERIES INFERENCE WITH HAC STANDARD ERRORS
# =============================================================================

@dataclass
class DailySeriesInferenceResult:
    """
    Results from daily P&L inference with HAC (Newey-West) standard errors.

    This provides robust standard errors that account for autocorrelation
    in daily returns, which is more appropriate than assuming i.i.d.
    """
    method: str = "hac_newey_west"
    n_days: int = 0
    n_trades: int = 0

    # Point estimates
    mean_daily_pnl: float = 0.0
    total_pnl: float = 0.0
    std_daily_pnl: float = 0.0

    # HAC standard error
    hac_std_error: float = 0.0
    hac_bandwidth: int = 0  # Newey-West lag truncation

    # Inference
    t_statistic: float = 0.0
    p_value: float = 1.0
    ci_lower_95: float = 0.0
    ci_upper_95: float = 0.0

    # Significance flags
    is_significant_5pct: bool = False
    is_significant_1pct: bool = False

    # Sample adequacy
    insufficient_sample: bool = False
    sample_size_warning: str = ""

    # Interpretation
    interpretation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "method": self.method,
            "description": (
                "Daily P&L inference with HAC (Newey-West) standard errors. "
                "Accounts for autocorrelation in daily returns. "
                "More robust than assuming i.i.d. trades."
            ),
            "n_days": self.n_days,
            "n_trades": self.n_trades,
            "mean_daily_pnl": round(self.mean_daily_pnl, 4),
            "total_pnl": round(self.total_pnl, 2),
            "std_daily_pnl": round(self.std_daily_pnl, 4),
            "hac_std_error": round(self.hac_std_error, 4),
            "hac_bandwidth": self.hac_bandwidth,
            "t_statistic": round(self.t_statistic, 4),
            "p_value": f"{self.p_value:.6e}" if self.p_value < 1e-4 else round(self.p_value, 6),
            "p_value_numeric": self.p_value,
            "ci_lower_95": round(self.ci_lower_95, 4),
            "ci_upper_95": round(self.ci_upper_95, 4),
            "is_significant_5pct": bool(self.is_significant_5pct),
            "is_significant_1pct": bool(self.is_significant_1pct),
            "insufficient_sample": self.insufficient_sample,
            "sample_size_warning": self.sample_size_warning,
            "interpretation": self.interpretation,
        }


def _newey_west_se(residuals: np.ndarray, bandwidth: int | None = None) -> float:
    """
    Compute Newey-West HAC standard error for mean estimation.

    Args:
        residuals: Array of residuals (daily returns centered at zero).
        bandwidth: Lag truncation parameter. If None, uses floor(4*(n/100)^(2/9)).

    Returns:
        HAC standard error of the mean.
    """
    n = len(residuals)
    if n < 2:
        return 0.0

    # Default bandwidth: Newey-West rule of thumb
    if bandwidth is None:
        bandwidth = int(np.floor(4 * (n / 100) ** (2 / 9)))
        bandwidth = max(1, min(bandwidth, n - 1))

    # Compute autocovariances
    gamma = np.zeros(bandwidth + 1)
    for j in range(bandwidth + 1):
        gamma[j] = np.mean(residuals[j:] * residuals[:n - j]) if j < n else 0.0

    # Newey-West weighted sum
    nw_var = gamma[0]
    for j in range(1, bandwidth + 1):
        weight = 1 - j / (bandwidth + 1)  # Bartlett kernel
        nw_var += 2 * weight * gamma[j]

    # Standard error of mean
    se = np.sqrt(nw_var / n)
    return float(se)


def daily_series_inference(
    trades_df: pd.DataFrame,
    all_trading_days: list[str] | None = None,
    min_days_threshold: int = 20,
) -> DailySeriesInferenceResult:
    """
    Perform inference on daily P&L using HAC (Newey-West) standard errors.

    This is the PRIMARY inference method for strategy evaluation. It:
    1. Computes daily P&L (including 0-trade days)
    2. Uses Newey-West HAC standard errors to account for autocorrelation
    3. Computes t-statistic and p-value for H0: E[daily P&L] = 0

    Args:
        trades_df: DataFrame with 'pnl' and 'date' columns.
        all_trading_days: List of all trading days (YYYY-MM-DD strings).
            If provided, 0-trade days are included with P&L=0.
        min_days_threshold: Minimum days required for inference.

    Returns:
        DailySeriesInferenceResult with robust inference statistics.
    """
    result = DailySeriesInferenceResult()

    # Handle empty inputs
    if trades_df.empty and (all_trading_days is None or len(all_trading_days) == 0):
        result.insufficient_sample = True
        result.sample_size_warning = "No trades and no trading days"
        return result

    result.n_trades = len(trades_df)

    # Build daily P&L series
    if all_trading_days is not None and len(all_trading_days) > 0:
        all_days_index = pd.Index(all_trading_days, name="date")
        daily_pnl_series = pd.Series(0.0, index=all_days_index)

        if not trades_df.empty:
            daily_pnl_with_trades = trades_df.groupby("date")["pnl"].sum()
            for dt in daily_pnl_with_trades.index:
                if dt in daily_pnl_series.index:
                    daily_pnl_series[dt] = daily_pnl_with_trades[dt]

        daily_pnl = daily_pnl_series.values
    else:
        daily_pnl = trades_df.groupby("date")["pnl"].sum().values

    n_days = len(daily_pnl)
    result.n_days = n_days

    if n_days < min_days_threshold:
        result.insufficient_sample = True
        result.sample_size_warning = f"Insufficient days for inference (N={n_days} < {min_days_threshold})"

    if n_days < 5:
        result.sample_size_warning = "Too few days for meaningful inference"
        return result

    # Point estimates
    mean_pnl = float(np.mean(daily_pnl))
    std_pnl = float(np.std(daily_pnl, ddof=1))
    total_pnl = float(np.sum(daily_pnl))

    result.mean_daily_pnl = mean_pnl
    result.std_daily_pnl = std_pnl
    result.total_pnl = total_pnl

    # Compute HAC standard error (Newey-West)
    residuals = daily_pnl - mean_pnl
    bandwidth = int(np.floor(4 * (n_days / 100) ** (2 / 9)))
    bandwidth = max(1, min(bandwidth, n_days - 1))
    result.hac_bandwidth = bandwidth

    hac_se = _newey_west_se(residuals, bandwidth)
    result.hac_std_error = hac_se

    # T-statistic and p-value
    if hac_se > 0:
        t_stat = mean_pnl / hac_se
        result.t_statistic = t_stat

        # Two-sided p-value using t-distribution
        from scipy import stats
        df = n_days - 1
        result.p_value = float(2 * (1 - stats.t.cdf(abs(t_stat), df)))

        # 95% confidence interval
        t_crit = stats.t.ppf(0.975, df)
        result.ci_lower_95 = mean_pnl - t_crit * hac_se
        result.ci_upper_95 = mean_pnl + t_crit * hac_se
    else:
        result.p_value = 1.0

    # Significance flags
    result.is_significant_5pct = result.p_value < 0.05
    result.is_significant_1pct = result.p_value < 0.01

    # Interpretation
    if result.insufficient_sample:
        result.interpretation = f"Insufficient sample (N={n_days} days). Results are unreliable."
    elif result.is_significant_1pct:
        direction = "positive" if mean_pnl > 0 else "negative"
        result.interpretation = (
            f"Highly significant (p < 0.01) {direction} edge. "
            f"Mean daily P&L = ${mean_pnl:.2f} (95% CI: ${result.ci_lower_95:.2f} to ${result.ci_upper_95:.2f}). "
            f"HAC SE accounts for autocorrelation (bandwidth={bandwidth})."
        )
    elif result.is_significant_5pct:
        direction = "positive" if mean_pnl > 0 else "negative"
        result.interpretation = (
            f"Significant (p < 0.05) {direction} edge. "
            f"Mean daily P&L = ${mean_pnl:.2f} (95% CI: ${result.ci_lower_95:.2f} to ${result.ci_upper_95:.2f})."
        )
    else:
        result.interpretation = (
            f"No significant edge detected (p = {result.p_value:.4f}). "
            f"Mean daily P&L = ${mean_pnl:.2f}. "
            f"95% CI includes zero: [{result.ci_lower_95:.2f}, {result.ci_upper_95:.2f}]."
        )

    return result
