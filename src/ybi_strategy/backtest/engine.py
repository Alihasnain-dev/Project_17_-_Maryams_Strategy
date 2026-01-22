from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from ybi_strategy.config import Config
from ybi_strategy.features.indicators import compute_session_indicators, compute_trend_indicators
from ybi_strategy.polygon.client import PolygonClient
from ybi_strategy.backtest.fills import FillModel
from ybi_strategy.backtest.portfolio import simulate_portfolio_day
from ybi_strategy.strategy.ybi_small_caps import simulate_ybi_small_caps, DayRiskState
from ybi_strategy.timeutils import SessionTimes, parse_hhmm
from ybi_strategy.universe.watchlist import build_watchlist_open_gap
from ybi_strategy.reporting.metrics import compute_metrics, compute_daily_metrics
from ybi_strategy.reporting.analysis import (
    stratified_analysis,
    monte_carlo_simulation,
    walk_forward_validation,
    block_bootstrap_test,
    time_shift_negative_control,
    shuffle_dates_negative_control,
)


class BacktestEngine:
    def __init__(self, *, config: Config, polygon: PolygonClient, output_dir: Path) -> None:
        self.config = config
        self.polygon = polygon
        self.output_dir = output_dir

        tz_name = str(config.get("timezone", default="America/New_York"))
        self.session = SessionTimes(
            tz=ZoneInfo(tz_name),
            trade_start=parse_hhmm(str(config.get("session", "trade_start", default="09:30"))),
            trade_end=parse_hhmm(str(config.get("session", "trade_end", default="11:00"))),
            force_flat=parse_hhmm(str(config.get("session", "force_flat", default="16:00"))),
        )
        self.premarket_start = parse_hhmm(str(config.get("session", "premarket_start", default="04:00")))
        self.premarket_end = parse_hhmm(str(config.get("session", "premarket_end", default="09:29")))

        slip_model = str(config.get("execution", "slippage", "model", default="fixed_cents"))
        cents = float(config.get("execution", "slippage", "cents", default=0.02))
        pct = float(config.get("execution", "slippage", "pct", default=0.001))
        fees = float(config.get("execution", "fees_per_trade", default=0.0))

        # Handle tiered slippage thresholds if provided
        tier_thresholds_raw = config.get("execution", "slippage", "tier_thresholds", default=None)
        tier_cents_raw = config.get("execution", "slippage", "tier_cents", default=None)
        tier_thresholds = tuple(tier_thresholds_raw) if tier_thresholds_raw else (5.0, 10.0, 20.0)
        tier_cents = tuple(tier_cents_raw) if tier_cents_raw else (0.02, 0.03, 0.05, 0.10)

        self.fills = FillModel(
            model=slip_model,
            cents=cents,
            pct=pct,
            fees_per_trade=fees,
            tier_thresholds=tier_thresholds,
            tier_cents=tier_cents,
        )

        # Risk management parameters
        self.max_trades_per_day = int(config.get("risk", "max_trades_per_day", default=5))
        self.max_daily_loss_pct = float(config.get("risk", "max_daily_loss_pct", default=0.02))
        self.cooldown_minutes = int(config.get("risk", "cooldown_minutes_after_stop", default=2))
        self.account_equity = float(config.get("risk", "account_equity", default=10000.0))

        # Portfolio-level parameters
        self.max_positions = int(config.get("portfolio", "max_positions", default=3))
        self.max_position_pct = float(config.get("portfolio", "max_position_pct", default=0.25))
        self.risk_per_trade_pct = float(config.get("portfolio", "risk_per_trade_pct", default=0.01))
        self.use_portfolio_mode = bool(config.get("portfolio", "enabled", default=True))

    # Monte Carlo seed for reproducibility
    MONTE_CARLO_SEED = 42

    def _generate_run_metadata(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Generate run metadata for reproducibility."""
        # Get git commit hash if available
        try:
            git_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent.parent
            ).stdout.strip()
        except Exception:
            git_commit = "unknown"

        # Get full config hash (not truncated)
        config_str = json.dumps(self.config.raw, sort_keys=True)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()

        run_id = str(uuid.uuid4())

        return {
            "run_id": run_id,
            "output_directory": str(self.output_dir),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": str(self.config.get("timezone", default="America/New_York")),
            "config_hash": f"sha256:{config_hash}",
            "config_content": self.config.raw,  # Full config for reproducibility
            "git_commit": git_commit,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "polygon_params": {
                "adjusted": True,  # Hardcoded in client
            },
            "portfolio_mode": self.use_portfolio_mode,
            "slippage_model": self.fills.model,
            "slippage_cents": self.fills.cents,
            "slippage_pct": self.fills.pct,
            "slippage_description": self.fills.describe(),
            "fees_per_trade": self.fills.fees_per_trade,
            "account_equity": self.account_equity,
            "max_trades_per_day": self.max_trades_per_day,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_positions": self.max_positions,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "monte_carlo_seed": self.MONTE_CARLO_SEED,
        }

    def run(self, *, start_date: str, end_date: str) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate and save run metadata first (for provenance)
        run_metadata = self._generate_run_metadata(start_date, end_date)
        metadata_path = self.output_dir / "run_metadata.json"
        metadata_path.write_text(json.dumps(run_metadata, indent=2), encoding="utf-8")

        days = pd.date_range(start=start_date, end=end_date, freq="D", tz=str(self.config.get("timezone")))
        all_trades: list[dict[str, Any]] = []
        all_fills: list[dict[str, Any]] = []
        all_watchlist: list[dict[str, Any]] = []
        day_audit: list[dict[str, Any]] = []  # Track day-by-day status

        for day_ts in days:
            d = day_ts.date()

            # Skip weekends
            if day_ts.dayofweek >= 5:
                day_audit.append({
                    "date": d.isoformat(),
                    "status": "weekend",
                    "reason": "Saturday" if day_ts.dayofweek == 5 else "Sunday",
                    "watchlist_count": 0,
                    "trades": 0,
                })
                continue

            # Run the day and capture results
            try:
                fills, trades, watchlist_rows = self._run_day(d)

                # Determine status based on results
                if not watchlist_rows:
                    status = "no_watchlist"
                    reason = "No stocks met watchlist criteria"
                elif not trades:
                    status = "no_trades"
                    reason = "Watchlist found but no trades generated"
                else:
                    status = "ok"
                    reason = ""

                day_audit.append({
                    "date": d.isoformat(),
                    "status": status,
                    "reason": reason,
                    "watchlist_count": len(watchlist_rows),
                    "trades": len(trades),
                })

                all_trades.extend(trades)
                all_fills.extend(fills)
                all_watchlist.extend(watchlist_rows)

            except Exception as e:
                # Capture any API errors or data issues
                day_audit.append({
                    "date": d.isoformat(),
                    "status": "error",
                    "reason": str(e)[:200],  # Truncate long error messages
                    "watchlist_count": 0,
                    "trades": 0,
                })

        out_path = self.output_dir / "trades.csv"
        trades_df = pd.DataFrame(all_trades)
        trades_df.to_csv(out_path, index=False)
        fills_path = self.output_dir / "fills.csv"
        pd.DataFrame(all_fills).to_csv(fills_path, index=False)
        watchlist_path = self.output_dir / "watchlist.csv"
        watchlist_df = pd.DataFrame(all_watchlist)
        watchlist_df.to_csv(watchlist_path, index=False)

        # Save day audit for data completeness tracking
        day_audit_path = self.output_dir / "day_audit.csv"
        pd.DataFrame(day_audit).to_csv(day_audit_path, index=False)

        # Compute day audit summary
        audit_df = pd.DataFrame(day_audit)
        total_days = len(audit_df)
        ok_days = len(audit_df[audit_df["status"] == "ok"])
        weekend_days = len(audit_df[audit_df["status"] == "weekend"])
        trading_days_attempted = total_days - weekend_days
        days_with_trades = ok_days
        days_with_errors = len(audit_df[audit_df["status"] == "error"])

        # CRITICAL: Extract ELIGIBLE trading days (exclude error days)
        # Error days are MISSING DATA, not "flat performance" - they must be excluded
        # from the daily P&L series to avoid biasing Sharpe/significance statistics.
        # Valid statuses for inclusion: ok, no_trades, no_watchlist
        eligible_statuses = ["ok", "no_trades", "no_watchlist"]
        eligible_trading_days = audit_df[audit_df["status"].isin(eligible_statuses)]["date"].tolist()

        # all_trading_days is now only eligible days (error days excluded)
        all_trading_days = eligible_trading_days

        # Compute comprehensive metrics
        summary_path = self.output_dir / "summary.json"
        summary = self._summarize(trades_df, watchlist_df, all_trading_days=all_trading_days)

        # Compute eligible trading days (excluding errors - missing data)
        days_no_trades = len(audit_df[audit_df["status"] == "no_trades"])
        days_no_watchlist = len(audit_df[audit_df["status"] == "no_watchlist"])
        eligible_trading_days_count = ok_days + days_no_trades + days_no_watchlist

        # Add day audit summary to the report with clear definitions
        summary["day_audit"] = {
            "total_calendar_days": total_days,
            "weekend_days": weekend_days,
            "trading_days_attempted": trading_days_attempted,
            "days_with_trades": days_with_trades,
            "days_with_no_trades": days_no_trades,
            "days_with_no_watchlist": days_no_watchlist,
            "days_with_errors": days_with_errors,
            # Data availability: eligible days / attempted days (errors are missing data)
            "data_completeness_pct": round(eligible_trading_days_count / trading_days_attempted * 100, 1) if trading_days_attempted > 0 else 0.0,
            # NEW: Explicit definition of which days are in the daily P&L series
            "eligible_trading_days": eligible_trading_days_count,
            "daily_series_definition": "Days with status in [ok, no_trades, no_watchlist]. Error days (API failures) are EXCLUDED as missing data, not treated as 0 P&L.",
        }

        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

        # Compute daily metrics (including 0-trade days)
        daily_metrics = compute_daily_metrics(trades_df, all_trading_days=all_trading_days)
        if not daily_metrics.empty:
            daily_path = self.output_dir / "daily_metrics.csv"
            daily_metrics.to_csv(daily_path, index=False)

    def _summarize(
        self,
        trades_df: pd.DataFrame,
        watchlist_df: pd.DataFrame | None = None,
        all_trading_days: list[str] | None = None,
    ) -> dict[str, Any]:
        if trades_df.empty:
            return {"trades": 0}

        # Compute comprehensive metrics with all trading days for proper Sharpe/Sortino
        metrics = compute_metrics(
            trades_df,
            account_equity=self.account_equity,
            all_trading_days=all_trading_days,
        )

        # Compute stratified analysis
        strat_analysis = stratified_analysis(
            trades_df,
            watchlist_df=watchlist_df,
            account_equity=self.account_equity,
        )

        # Run Monte Carlo simulation
        mc_result = monte_carlo_simulation(
            trades_df,
            n_simulations=10000,
            account_equity=self.account_equity,
            random_seed=self.MONTE_CARLO_SEED,
        )

        # Run walk-forward validation
        wf_result = walk_forward_validation(
            trades_df,
            n_folds=5,
            train_pct=0.7,
            account_equity=self.account_equity,
        )

        # Run bootstrap hypothesis test on daily P&L
        # NOTE: This is an INFERENCE method testing H0: E[daily P&L] = 0,
        # NOT a leakage-detecting negative control.
        # Pass all_trading_days for consistency with compute_metrics()
        bootstrap_result = block_bootstrap_test(
            trades_df,
            n_bootstrap=10000,
            random_seed=self.MONTE_CARLO_SEED,
            all_trading_days=all_trading_days,  # Include 0-trade days for consistency
        )

        # Run TRUE negative controls (break signal→return structure)
        time_shift_result = time_shift_negative_control(
            trades_df,
            shift_minutes=5,
            n_simulations=1000,
            random_seed=self.MONTE_CARLO_SEED,
        )
        shuffle_result = shuffle_dates_negative_control(
            trades_df,
            n_simulations=1000,
            random_seed=self.MONTE_CARLO_SEED,
        )

        return {
            "metrics": metrics.to_dict(),
            "stratified_analysis": strat_analysis.to_dict(),
            "monte_carlo": mc_result.to_dict(),
            "walk_forward": wf_result.to_dict(),
            # Statistical inference (hypothesis tests)
            "statistical_inference": {
                "bootstrap_mean_test": {
                    "description": "Day-level block bootstrap testing H0: E[daily P&L] = 0. This is a HYPOTHESIS TEST for edge detection, not a leakage control.",
                    "note": "observed_mean_daily_pnl should match metrics.mean_daily_pnl (same day set)",
                    **bootstrap_result.to_dict(),
                },
            },
            # TRUE negative controls (break signal→return to detect leakage)
            "negative_controls": {
                "description": "Tests that break signal→return structure. If strategy still shows edge after breaking, investigate leakage.",
                "time_shift_5min": time_shift_result.to_dict(),
                "shuffle_dates": shuffle_result.to_dict(),
            },
        }

    def _run_day(self, d: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        wl = build_watchlist_open_gap(
            polygon=self.polygon,
            day=d,
            top_n=int(self.config.get("watchlist", "top_n", default=20)),
            min_gap_pct=float(self.config.get("watchlist", "min_gap_pct", default=0.05)),
            min_prev_close=float(self.config.get("watchlist", "min_prev_close", default=0.5)),
            max_prev_close=float(self.config.get("watchlist", "max_prev_close", default=20.0)),
        )

        watchlist_rows: list[dict[str, Any]] = [
            {"date": d.isoformat(), "ticker": i.ticker, "gap_pct": i.gap_pct, "prev_close": i.prev_close, "open_price": i.open_price}
            for i in wl
        ]

        # Compute previous trading day for PDH/PDL
        prev_day = self._prev_trading_day(d)

        # Prepare bars for all tickers
        ticker_bars: dict[str, pd.DataFrame] = {}
        for item in wl:
            bars = self.polygon.minute_bars(item.ticker, d)
            if not bars:
                continue

            df_full = self._bars_to_frame(bars)
            df_full = self._add_premarket_stats(df_full, d)
            df_full = compute_trend_indicators(df_full)

            # Fetch previous day's bar for PDH/PDL
            prev_daily = self.polygon.daily_bar(item.ticker, prev_day)
            if prev_daily:
                df_full["pdh"] = float(prev_daily["h"])
                df_full["pdl"] = float(prev_daily["l"])
            else:
                df_full["pdh"] = np.nan
                df_full["pdl"] = np.nan

            df = self._filter_session(df_full, d)
            if df.empty:
                continue

            df = compute_session_indicators(df)
            ticker_bars[item.ticker] = df

        if not ticker_bars:
            return [], [], watchlist_rows

        # Use portfolio mode or legacy per-ticker mode
        if self.use_portfolio_mode:
            # Portfolio-level simulation (processes all tickers minute-by-minute)
            fills_list, trades_list, _ = simulate_portfolio_day(
                day=d,
                ticker_bars=ticker_bars,
                config=self.config,
                fills=self.fills,
                starting_equity=self.account_equity,
                max_trades_per_day=self.max_trades_per_day,
                max_daily_loss_pct=self.max_daily_loss_pct,
                cooldown_minutes=self.cooldown_minutes,
                force_flat_time=self.session.force_flat,
                max_positions=self.max_positions,
                max_position_pct=self.max_position_pct,
                risk_per_trade_pct=self.risk_per_trade_pct,
            )
            fills = [f.__dict__ for f in fills_list]
            trades = trades_list
        else:
            # Legacy per-ticker simulation (for backward compatibility)
            trades: list[dict[str, Any]] = []
            fills: list[dict[str, Any]] = []
            day_risk_state = DayRiskState()

            for ticker, df in ticker_bars.items():
                fills_i, trades_i = simulate_ybi_small_caps(
                    ticker=ticker,
                    day=d,
                    df=df,
                    config=self.config,
                    fills=self.fills,
                    max_trades_per_day=self.max_trades_per_day,
                    max_daily_loss_pct=self.max_daily_loss_pct,
                    cooldown_minutes=self.cooldown_minutes,
                    account_equity=self.account_equity,
                    force_flat_time=self.session.force_flat,
                    day_risk_state=day_risk_state,
                )
                fills.extend([f.__dict__ for f in fills_i])
                trades.extend(trades_i)

        return fills, trades, watchlist_rows

    def _bars_to_frame(self, bars: list[dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame(bars)
        # Polygon aggregate fields: o,h,l,c,v,t (ms since epoch)
        df = df.rename(columns={"o": "o", "h": "h", "l": "l", "c": "c", "v": "v", "t": "t"})
        df = df[["t", "o", "h", "l", "c", "v"]]

        tz_name = str(self.config.get("timezone", default="America/New_York"))
        df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(tz_name)
        df = df.drop(columns=["t"]).set_index("ts").sort_index()
        return df

    def _filter_session(self, df: pd.DataFrame, d: date) -> pd.DataFrame:
        # CRITICAL: Use pd.Timestamp with tz_localize to avoid pytz LMT offset bug
        # Using datetime(..., tzinfo=pytz_tz) creates LMT offset (-04:56) instead of proper EST/EDT
        tz_name = str(self.config.get("timezone", default="America/New_York"))
        start = pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=self.session.trade_start.hour, minute=self.session.trade_start.minute
        ).tz_localize(tz_name)
        end = pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=self.session.trade_end.hour, minute=self.session.trade_end.minute
        ).tz_localize(tz_name)
        return df[(df.index >= start) & (df.index <= end)]

    def _add_premarket_stats(self, df: pd.DataFrame, d: date) -> pd.DataFrame:
        if df.empty:
            return df
        # CRITICAL: Use pd.Timestamp with tz_localize to avoid pytz LMT offset bug
        tz_name = str(self.config.get("timezone", default="America/New_York"))
        pm_start = pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=self.premarket_start.hour, minute=self.premarket_start.minute
        ).tz_localize(tz_name)
        pm_end = pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=self.premarket_end.hour, minute=self.premarket_end.minute
        ).tz_localize(tz_name)
        pre = df[(df.index >= pm_start) & (df.index <= pm_end)]
        if pre.empty:
            df["pmh"] = np.nan  # type: ignore[name-defined]
            df["pml"] = np.nan  # type: ignore[name-defined]
            df["premarket_vol"] = 0.0
            df["premarket_last"] = np.nan  # type: ignore[name-defined]
            return df

        pmh = float(pre["h"].max())
        pml = float(pre["l"].min())
        premarket_vol = float(pre["v"].sum())
        premarket_last = float(pre["c"].iloc[-1])

        df["pmh"] = pmh
        df["pml"] = pml
        df["premarket_vol"] = premarket_vol
        df["premarket_last"] = premarket_last
        return df

    def _prev_trading_day(self, d: date) -> date:
        """Get previous trading day (simple: skip weekends)."""
        prev = d - timedelta(days=1)
        while prev.weekday() >= 5:  # Saturday=5, Sunday=6
            prev -= timedelta(days=1)
        return prev

    # Trades are simulated in `strategy/ybi_small_caps.py`.
