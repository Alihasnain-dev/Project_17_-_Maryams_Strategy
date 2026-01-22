"""Core performance metrics for YBI strategy evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class PerformanceMetrics:
    """Container for computed performance metrics."""

    # Basic counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    # Win/loss rates
    win_rate: float = 0.0
    loss_rate: float = 0.0

    # P&L statistics
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    median_pnl: float = 0.0
    std_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Expectancy and edge metrics
    expectancy: float = 0.0
    expectancy_per_dollar_risked: float = 0.0
    profit_factor: float = 0.0

    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Drawdown metrics
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_drawdown: float = 0.0
    max_drawdown_duration_trades: int = 0

    # Streak analysis
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_win_streak: float = 0.0
    avg_loss_streak: float = 0.0

    # Statistical significance (two-sided test: H0: mean=0, H1: mean!=0)
    t_statistic: float = 0.0
    p_value: float = 1.0  # Two-sided p-value
    is_significant_5pct: bool = False  # Reject H0 at 5% (two-sided)
    is_significant_1pct: bool = False  # Reject H0 at 1% (two-sided)
    mean_daily_pnl: float = 0.0  # Mean daily P&L
    pnl_sign: str = "zero"  # "positive", "negative", or "zero"
    trading_days_in_sample: int = 0  # Total trading days (including 0-trade days)

    # Win rate by setup type
    win_rate_by_setup: dict[str, float] = field(default_factory=dict)
    trade_count_by_setup: dict[str, int] = field(default_factory=dict)

    # Sample size adequacy flag
    insufficient_sample: bool = False
    sample_size_warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        # Format p_value with proper precision:
        # - Very small values (< 1e-6) use scientific notation
        # - Larger values use standard decimal (6 decimal places)
        p_val = float(self.p_value)
        if p_val < 1e-6 and p_val > 0:
            p_value_str = f"{p_val:.2e}"  # Scientific notation for very small values
        else:
            p_value_str = f"{p_val:.6f}"

        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": self.breakeven_trades,
            "win_rate": round(self.win_rate, 4),
            "loss_rate": round(self.loss_rate, 4),
            "total_pnl": round(self.total_pnl, 2),
            "avg_pnl": round(self.avg_pnl, 4),
            "median_pnl": round(self.median_pnl, 4),
            "std_pnl": round(self.std_pnl, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "largest_win": round(self.largest_win, 4),
            "largest_loss": round(self.largest_loss, 4),
            "expectancy": round(self.expectancy, 4),
            "expectancy_per_dollar_risked": round(self.expectancy_per_dollar_risked, 4),
            "profit_factor": round(self.profit_factor, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "avg_drawdown": round(self.avg_drawdown, 4),
            "max_drawdown_duration_trades": self.max_drawdown_duration_trades,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "avg_win_streak": round(self.avg_win_streak, 2),
            "avg_loss_streak": round(self.avg_loss_streak, 2),
            "t_statistic": round(float(self.t_statistic), 4),
            "p_value": p_value_str,  # String with proper precision
            "p_value_numeric": p_val,  # Raw numeric value for programmatic access
            "is_significant_5pct": bool(self.is_significant_5pct),
            "is_significant_1pct": bool(self.is_significant_1pct),
            "mean_daily_pnl": round(self.mean_daily_pnl, 4),
            "pnl_sign": self.pnl_sign,
            "trading_days_in_sample": self.trading_days_in_sample,
            "win_rate_by_setup": {k: round(float(v), 4) for k, v in self.win_rate_by_setup.items()},
            "trade_count_by_setup": {k: int(v) for k, v in self.trade_count_by_setup.items()},
            "insufficient_sample": self.insufficient_sample,
            "sample_size_warning": self.sample_size_warning,
        }


def compute_metrics(
    trades_df: pd.DataFrame,
    account_equity: float = 10000.0,
    risk_free_rate: float = 0.0,
    annualization_factor: float = 252.0,
    min_sample_threshold: int = 30,
    all_trading_days: list[str] | None = None,
) -> PerformanceMetrics:
    """
    Compute comprehensive performance metrics from trade data.

    Args:
        trades_df: DataFrame with columns: pnl, entry_reason, exit_reason, qty, etc.
        account_equity: Starting account equity for drawdown calculations.
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default 0).
        annualization_factor: Trading days per year (default 252).
        min_sample_threshold: Minimum number of trades for reliable statistics (default 30).
            When N < threshold, metrics are flagged as insufficient_sample.
        all_trading_days: Optional list of all trading days (YYYY-MM-DD strings) in the
            backtest period. If provided, Sharpe/Sortino include 0-trade days. This
            should include weekends/holidays-excluded days where trading was attempted.

    Returns:
        PerformanceMetrics dataclass with all computed metrics.
    """
    metrics = PerformanceMetrics()

    if trades_df.empty:
        metrics.insufficient_sample = True
        metrics.sample_size_warning = "No trades (N=0)"
        return metrics

    pnl = trades_df["pnl"].astype(float)
    n = len(pnl)

    # Check sample size adequacy
    if n < min_sample_threshold:
        metrics.insufficient_sample = True
        metrics.sample_size_warning = f"Insufficient sample (N={n} < {min_sample_threshold})"

    # Basic counts
    metrics.total_trades = n
    metrics.winning_trades = int((pnl > 0).sum())
    metrics.losing_trades = int((pnl < 0).sum())
    metrics.breakeven_trades = int((pnl == 0).sum())

    # Win/loss rates
    metrics.win_rate = metrics.winning_trades / n if n > 0 else 0.0
    metrics.loss_rate = metrics.losing_trades / n if n > 0 else 0.0

    # P&L statistics
    metrics.total_pnl = float(pnl.sum())
    metrics.avg_pnl = float(pnl.mean())
    metrics.median_pnl = float(pnl.median())
    metrics.std_pnl = float(pnl.std()) if n > 1 else 0.0

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    metrics.avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    metrics.avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0
    metrics.largest_win = float(wins.max()) if len(wins) > 0 else 0.0
    metrics.largest_loss = float(losses.min()) if len(losses) > 0 else 0.0

    # Expectancy: E = (Win% × AvgWin) - (Loss% × |AvgLoss|)
    metrics.expectancy = (metrics.win_rate * metrics.avg_win) + (metrics.loss_rate * metrics.avg_loss)

    # Expectancy per dollar risked (using average loss as risk proxy)
    if metrics.avg_loss != 0:
        metrics.expectancy_per_dollar_risked = metrics.expectancy / abs(metrics.avg_loss)

    # Profit factor: Gross Profit / |Gross Loss|
    gross_profit = float(wins.sum()) if len(wins) > 0 else 0.0
    gross_loss = abs(float(losses.sum())) if len(losses) > 0 else 0.0
    metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    # Drawdown calculations
    equity_curve = account_equity + pnl.cumsum()
    running_max = equity_curve.cummax()
    drawdown = equity_curve - running_max
    drawdown_pct = drawdown / running_max

    metrics.max_drawdown = float(drawdown.min())
    metrics.max_drawdown_pct = float(drawdown_pct.min())
    metrics.avg_drawdown = float(drawdown[drawdown < 0].mean()) if (drawdown < 0).any() else 0.0

    # Max drawdown duration (in trades)
    metrics.max_drawdown_duration_trades = _compute_max_dd_duration(equity_curve)

    # =================================================================
    # CORRECTED: Risk-adjusted metrics computed on DAILY RETURNS
    # Previous implementation incorrectly annualized per-trade P&L
    # CRITICAL FIX: Include 0-trade days in Sharpe/Sortino calculations
    # =================================================================

    # Compute daily P&L and daily returns
    if "date" in trades_df.columns:
        # Get daily P&L for days with trades
        daily_pnl_with_trades = trades_df.groupby("date")["pnl"].sum()

        # Build complete daily P&L series including 0-trade days
        if all_trading_days is not None and len(all_trading_days) > 0:
            # Create series with all trading days, defaulting to 0 P&L
            all_days_index = pd.Index(all_trading_days, name="date")
            daily_pnl = pd.Series(0.0, index=all_days_index)
            # Fill in the days that have trades
            for dt in daily_pnl_with_trades.index:
                if dt in daily_pnl.index:
                    daily_pnl[dt] = daily_pnl_with_trades[dt]
            daily_pnl = daily_pnl.sort_index()
        else:
            # Fallback: use only days with trades (less accurate but backward compatible)
            daily_pnl = daily_pnl_with_trades

        n_trading_days = len(daily_pnl)
        metrics.trading_days_in_sample = n_trading_days

        if n_trading_days > 1:
            # Build daily equity curve
            daily_equity = account_equity + daily_pnl.cumsum()

            # Compute daily returns (percentage)
            # First day's return is from starting equity
            daily_returns = pd.Series(index=daily_pnl.index, dtype=float)
            prev_equity = account_equity
            for dt in daily_pnl.index:
                current_equity = prev_equity + daily_pnl[dt]
                daily_returns[dt] = (current_equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
                prev_equity = current_equity

            mean_daily_return = float(daily_returns.mean())
            std_daily_return = float(daily_returns.std())

            # Sharpe ratio: (mean_daily - rf_daily) / std_daily * sqrt(252)
            rf_daily = risk_free_rate / annualization_factor
            if std_daily_return > 0:
                metrics.sharpe_ratio = (mean_daily_return - rf_daily) / std_daily_return * np.sqrt(annualization_factor)

            # Sortino ratio: uses only downside deviation
            downside_returns = daily_returns[daily_returns < 0]
            if len(downside_returns) > 0:
                downside_std = float(downside_returns.std())
                if downside_std > 0:
                    metrics.sortino_ratio = (mean_daily_return - rf_daily) / downside_std * np.sqrt(annualization_factor)

            # Calmar ratio: annualized return / |max drawdown %|
            # Annualize based on actual trading days
            if metrics.max_drawdown_pct != 0:
                total_return = daily_returns.sum()  # Approximate, assumes small returns
                annualized_return = total_return * (annualization_factor / n_trading_days)
                metrics.calmar_ratio = annualized_return / abs(metrics.max_drawdown_pct)
    else:
        # Fallback: if no date column, use per-trade (with warning comment)
        # This is DEPRECATED and should not be relied upon
        if metrics.std_pnl > 0:
            excess_return = metrics.avg_pnl - (risk_free_rate / annualization_factor * account_equity)
            # NOTE: This is an approximation and not statistically valid
            metrics.sharpe_ratio = (excess_return / metrics.std_pnl) * np.sqrt(min(n, annualization_factor))

    # Streak analysis
    metrics.max_consecutive_wins, metrics.max_consecutive_losses = _compute_streaks(pnl)
    metrics.avg_win_streak, metrics.avg_loss_streak = _compute_avg_streaks(pnl)

    # =================================================================
    # CORRECTED: Statistical significance using day-level clustering
    # TWO-SIDED TEST: H0: mean=0, H1: mean!=0
    # Previous implementation only flagged significance when mean > 0
    # =================================================================

    if "date" in trades_df.columns:
        # Use full daily_pnl (including 0-trade days if available)
        if all_trading_days is not None and len(all_trading_days) > 0:
            all_days_index = pd.Index(all_trading_days, name="date")
            daily_pnl_full = pd.Series(0.0, index=all_days_index)
            daily_pnl_with_trades = trades_df.groupby("date")["pnl"].sum()
            for dt in daily_pnl_with_trades.index:
                if dt in daily_pnl_full.index:
                    daily_pnl_full[dt] = daily_pnl_with_trades[dt]
        else:
            daily_pnl_full = trades_df.groupby("date")["pnl"].sum()

        n_days = len(daily_pnl_full)
        mean_daily = float(daily_pnl_full.mean())
        metrics.mean_daily_pnl = mean_daily
        metrics.trading_days_in_sample = n_days

        # Determine sign
        if mean_daily > 0:
            metrics.pnl_sign = "positive"
        elif mean_daily < 0:
            metrics.pnl_sign = "negative"
        else:
            metrics.pnl_sign = "zero"

        if n_days > 1:
            # Two-sided t-test on daily P&L (H0: mean=0)
            t_stat, p_val = stats.ttest_1samp(daily_pnl_full, 0)
            metrics.t_statistic = float(t_stat)
            metrics.p_value = float(p_val)  # Two-sided p-value
            # Significance: reject H0 (mean=0) at given alpha level (two-sided)
            metrics.is_significant_5pct = p_val < 0.05
            metrics.is_significant_1pct = p_val < 0.01
    else:
        # Fallback to per-trade (DEPRECATED)
        if n > 1 and metrics.std_pnl > 0:
            t_stat, p_val = stats.ttest_1samp(pnl, 0)
            metrics.t_statistic = float(t_stat)
            metrics.p_value = float(p_val)
            metrics.mean_daily_pnl = metrics.avg_pnl  # Approximate
            metrics.pnl_sign = "positive" if metrics.avg_pnl > 0 else ("negative" if metrics.avg_pnl < 0 else "zero")
            metrics.is_significant_5pct = p_val < 0.05
            metrics.is_significant_1pct = p_val < 0.01

    # Win rate by setup type
    if "entry_reason" in trades_df.columns:
        metrics.win_rate_by_setup, metrics.trade_count_by_setup = _compute_win_rate_by_setup(trades_df)

    return metrics


def _compute_max_dd_duration(equity_curve: pd.Series) -> int:
    """Compute maximum drawdown duration in number of trades."""
    running_max = equity_curve.cummax()
    in_drawdown = equity_curve < running_max

    max_duration = 0
    current_duration = 0

    for is_dd in in_drawdown:
        if is_dd:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0

    return max_duration


def _compute_streaks(pnl: pd.Series) -> tuple[int, int]:
    """Compute maximum consecutive wins and losses."""
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for p in pnl:
        if p > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif p < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0

    return max_wins, max_losses


def _compute_avg_streaks(pnl: pd.Series) -> tuple[float, float]:
    """Compute average win and loss streak lengths."""
    win_streaks: list[int] = []
    loss_streaks: list[int] = []
    current_wins = 0
    current_losses = 0

    for p in pnl:
        if p > 0:
            if current_losses > 0:
                loss_streaks.append(current_losses)
                current_losses = 0
            current_wins += 1
        elif p < 0:
            if current_wins > 0:
                win_streaks.append(current_wins)
                current_wins = 0
            current_losses += 1
        else:
            if current_wins > 0:
                win_streaks.append(current_wins)
            if current_losses > 0:
                loss_streaks.append(current_losses)
            current_wins = 0
            current_losses = 0

    # Don't forget the last streak
    if current_wins > 0:
        win_streaks.append(current_wins)
    if current_losses > 0:
        loss_streaks.append(current_losses)

    avg_win = float(np.mean(win_streaks)) if win_streaks else 0.0
    avg_loss = float(np.mean(loss_streaks)) if loss_streaks else 0.0

    return avg_win, avg_loss


def _compute_win_rate_by_setup(trades_df: pd.DataFrame) -> tuple[dict[str, float], dict[str, int]]:
    """Compute win rate grouped by entry reason/setup type."""
    win_rates: dict[str, float] = {}
    trade_counts: dict[str, int] = {}

    # Extract base setup type from entry_reason (before the |ttm= part)
    def extract_setup(reason: str) -> str:
        if pd.isna(reason):
            return "unknown"
        parts = str(reason).split("|")
        return parts[0] if parts else "unknown"

    trades_df = trades_df.copy()
    trades_df["setup_type"] = trades_df["entry_reason"].apply(extract_setup)

    for setup, group in trades_df.groupby("setup_type"):
        setup_str = str(setup)
        n = len(group)
        wins = (group["pnl"].astype(float) > 0).sum()
        win_rates[setup_str] = wins / n if n > 0 else 0.0
        trade_counts[setup_str] = n

    return win_rates, trade_counts


def compute_daily_metrics(
    trades_df: pd.DataFrame,
    all_trading_days: list[str] | None = None,
) -> pd.DataFrame:
    """
    Compute metrics aggregated by day.

    Args:
        trades_df: DataFrame with trade data (must have 'date' and 'pnl' columns).
        all_trading_days: Optional list of all trading days (YYYY-MM-DD strings).
            If provided, the output will include rows for 0-trade days.
            This ensures the daily metrics CSV matches trading_days_in_sample.

    Returns:
        DataFrame with daily P&L, trade count, win rate, etc.
        Includes 0-trade days if all_trading_days is provided.
    """
    if trades_df.empty or "date" not in trades_df.columns:
        # Return empty DataFrame with 0-trade days if provided
        if all_trading_days is not None and len(all_trading_days) > 0:
            daily = pd.DataFrame({
                "date": all_trading_days,
                "trade_count": 0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
            })
            return daily
        return pd.DataFrame()

    # Compute metrics for days with trades
    daily_with_trades = trades_df.groupby("date").agg(
        trade_count=("pnl", "count"),
        total_pnl=("pnl", "sum"),
        avg_pnl=("pnl", "mean"),
        win_count=("pnl", lambda x: (x > 0).sum()),
        loss_count=("pnl", lambda x: (x < 0).sum()),
    ).reset_index()

    daily_with_trades["win_rate"] = daily_with_trades["win_count"] / daily_with_trades["trade_count"]
    daily_with_trades["win_rate"] = daily_with_trades["win_rate"].fillna(0.0)

    # If all_trading_days provided, include 0-trade days
    if all_trading_days is not None and len(all_trading_days) > 0:
        # Create full DataFrame with all trading days
        all_days_df = pd.DataFrame({
            "date": all_trading_days,
        })

        # Merge with days that have trades
        daily = all_days_df.merge(daily_with_trades, on="date", how="left")

        # Fill NaN values for 0-trade days
        daily["trade_count"] = daily["trade_count"].fillna(0).astype(int)
        daily["total_pnl"] = daily["total_pnl"].fillna(0.0)
        daily["avg_pnl"] = daily["avg_pnl"].fillna(0.0)
        daily["win_count"] = daily["win_count"].fillna(0).astype(int)
        daily["loss_count"] = daily["loss_count"].fillna(0).astype(int)
        daily["win_rate"] = daily["win_rate"].fillna(0.0)

        return daily

    return daily_with_trades


def compute_rolling_metrics(
    trades_df: pd.DataFrame,
    window: int = 20,
) -> pd.DataFrame:
    """
    Compute rolling performance metrics over a window of trades.

    Args:
        trades_df: DataFrame with pnl column.
        window: Number of trades for rolling window.

    Returns:
        DataFrame with rolling metrics.
    """
    if trades_df.empty or len(trades_df) < window:
        return pd.DataFrame()

    pnl = trades_df["pnl"].astype(float)

    rolling = pd.DataFrame({
        "trade_idx": range(len(pnl)),
        "pnl": pnl.values,
    })

    rolling["rolling_pnl"] = pnl.rolling(window).sum()
    rolling["rolling_avg"] = pnl.rolling(window).mean()
    rolling["rolling_std"] = pnl.rolling(window).std()
    rolling["rolling_win_rate"] = (pnl > 0).rolling(window).mean()

    # Rolling Sharpe (simplified)
    rolling["rolling_sharpe"] = (
        rolling["rolling_avg"] / rolling["rolling_std"]
    ).replace([np.inf, -np.inf], np.nan)

    return rolling.dropna()
