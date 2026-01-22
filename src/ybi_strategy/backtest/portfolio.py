"""Portfolio-level simulation with proper capital management.

This module implements a minute-by-minute portfolio simulation that:
1. Processes all tickers simultaneously at each timestamp
2. Tracks cash/equity and enforces capital constraints
3. Manages multiple concurrent positions with proper allocation
4. Uses mark-to-market equity for risk calculations

This replaces the per-ticker independent simulation that allowed impossible
overlapping positions without capital constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import numpy as np
import pandas as pd

from ybi_strategy.config import Config
from ybi_strategy.backtest.fills import FillModel
from ybi_strategy.strategy.ybi_small_caps import (
    Fill,
    Position,
    DayRiskState,
    PendingEntry,
    PendingExit,
    next_round_resistance,
)


@dataclass
class PortfolioPosition:
    """A position within the portfolio context."""
    ticker: str
    position: Position
    pending_entry: PendingEntry | None = None
    pending_exit: PendingExit | None = None
    pending_add: PendingEntry | None = None
    # Per-ticker state
    breakout_seen: bool = False
    prev_close: float | None = None
    prev_vwap: float | None = None
    prev_ema21: float | None = None


@dataclass
class PortfolioState:
    """
    Tracks portfolio state across all tickers for a single day.

    This enables proper capital management and prevents impossible overlaps.
    """
    # Cash and equity tracking
    starting_equity: float
    cash: float
    realized_pnl: float = 0.0

    # Position tracking: ticker -> PortfolioPosition
    positions: dict[str, PortfolioPosition] = field(default_factory=dict)

    # Risk state (shared across all tickers)
    risk_state: DayRiskState = field(default_factory=DayRiskState)

    # Capital constraints
    max_positions: int = 3
    max_position_pct: float = 0.25  # Max 25% of equity per position
    min_cash_reserve_pct: float = 0.10  # Keep 10% cash reserve

    def get_equity(self, current_prices: dict[str, float]) -> float:
        """
        Calculate mark-to-market equity.

        Args:
            current_prices: ticker -> current price mapping
        """
        unrealized = 0.0
        for ticker, pp in self.positions.items():
            if pp.position.is_open():
                price = current_prices.get(ticker)
                if price is not None:
                    unrealized += (price - pp.position.avg_entry) * pp.position.qty
        return self.cash + unrealized

    def get_open_position_count(self) -> int:
        """Count number of currently open positions."""
        return sum(1 for pp in self.positions.values() if pp.position.is_open())

    def can_open_position(self) -> bool:
        """Check if we can open a new position (capital/slot available)."""
        return self.get_open_position_count() < self.max_positions

    def get_max_position_value(self, current_prices: dict[str, float]) -> float:
        """Get maximum allowed position value based on current equity."""
        equity = self.get_equity(current_prices)
        return equity * self.max_position_pct

    def get_available_capital(self, current_prices: dict[str, float]) -> float:
        """Get capital available for new positions."""
        equity = self.get_equity(current_prices)
        reserve = equity * self.min_cash_reserve_pct
        return max(0.0, self.cash - reserve)


def simulate_portfolio_day(
    *,
    day: date,
    ticker_bars: dict[str, pd.DataFrame],
    config: Config,
    fills: FillModel,
    starting_equity: float = 10000.0,
    max_trades_per_day: int = 5,
    max_daily_loss_pct: float = 0.02,
    cooldown_minutes: int = 2,
    force_flat_time: time | None = None,
    max_positions: int = 3,
    max_position_pct: float = 0.25,
    risk_per_trade_pct: float = 0.01,  # 1% risk per trade
) -> tuple[list[Fill], list[dict[str, Any]], PortfolioState]:
    """
    Simulate a single day with portfolio-level management.

    Args:
        day: Trading day
        ticker_bars: Dict of ticker -> DataFrame with OHLCV and indicators
        config: Strategy configuration
        fills: Fill/slippage model
        starting_equity: Starting portfolio equity
        max_trades_per_day: Maximum trades allowed per day
        max_daily_loss_pct: Maximum daily loss as percentage of equity
        cooldown_minutes: Minutes to wait after a stop-out
        force_flat_time: Time to force all positions flat
        max_positions: Maximum concurrent positions
        max_position_pct: Maximum position size as percentage of equity
        risk_per_trade_pct: Risk per trade as percentage of equity

    Returns:
        Tuple of (fills_list, trades_list, final_portfolio_state)
    """
    # Load config settings
    allow_starter = bool(config.get("strategy_small_caps", "allow_starter_entries", default=True))
    starter_frac = float(config.get("strategy_small_caps", "starter_fraction", default=0.25))
    require_pmh_breakout = bool(config.get("strategy_small_caps", "entry", "require_pmh_breakout", default=False))
    max_ext = float(config.get("strategy_small_caps", "entry", "max_extension_from_ema8_pct", default=0.015))
    require_momo = bool(config.get("strategy_small_caps", "entry", "require_momentum_bull", default=True))

    req_ema34 = bool(config.get("strategy_small_caps", "macro_filter", "require_above_ema_34", default=True))
    req_ema55 = bool(config.get("strategy_small_caps", "macro_filter", "require_above_ema_55", default=True))
    req_sma200 = bool(config.get("strategy_small_caps", "macro_filter", "require_above_sma_200", default=False))

    exit_on_below_ema8 = bool(config.get("strategy_small_caps", "exits", "exit_on_close_below_ema8", default=True))
    exit_on_ttm_momo_bear = bool(config.get("strategy_small_caps", "exits", "exit_on_ttm_momentum_bear", default=True))
    scale_frac = float(config.get("strategy_small_caps", "exits", "scale_out_first_fraction", default=0.50))
    stop_buffer_pct = float(config.get("strategy_small_caps", "risk", "stop_buffer_pct", default=0.001))

    # Initialize portfolio state
    portfolio = PortfolioState(
        starting_equity=starting_equity,
        cash=starting_equity,
        max_positions=max_positions,
        max_position_pct=max_position_pct,
    )
    max_loss = starting_equity * max_daily_loss_pct

    # Initialize per-ticker state
    for ticker in ticker_bars:
        portfolio.positions[ticker] = PortfolioPosition(
            ticker=ticker,
            position=Position(),
        )

    fills_out: list[Fill] = []
    trades_out: list[dict[str, Any]] = []

    # Build unified timeline of all timestamps
    all_timestamps: set[pd.Timestamp] = set()
    for df in ticker_bars.values():
        all_timestamps.update(df.index.tolist())
    sorted_timestamps = sorted(all_timestamps)

    if not sorted_timestamps:
        return fills_out, trades_out, portfolio

    def record_fill(
        ticker: str,
        ts: pd.Timestamp,
        side: str,
        qty: float,
        px: float,
        reason: str,
        signal_ts: datetime | None = None,
    ) -> None:
        fills_out.append(Fill(
            date=day.isoformat(),
            ticker=ticker,
            ts=ts.isoformat(),
            side=side,
            qty=qty,
            price=px,
            reason=reason,
            signal_ts=signal_ts.isoformat() if signal_ts else None,
        ))

    def close_position(
        ticker: str,
        pp: PortfolioPosition,
        ts: pd.Timestamp,
        exit_px: float,
        reason: str,
        signal_ts: datetime | None = None,
    ) -> None:
        if not pp.position.is_open():
            return

        qty = pp.position.qty
        record_fill(ticker, ts, "SELL", qty, exit_px, reason, signal_ts)

        # Calculate P&L (includes fees)
        pnl = (exit_px - pp.position.avg_entry) * qty - fills.fees_per_trade

        # Update portfolio cash - MUST subtract fees to maintain ledger consistency
        # The fee is deducted from proceeds to match the P&L calculation
        portfolio.cash += (exit_px * qty - fills.fees_per_trade)
        portfolio.realized_pnl += pnl

        # Update risk state
        portfolio.risk_state.record_trade(
            pnl, was_stop=(reason == "stop_hit"), exit_ts=ts.to_pydatetime()
        )

        # Record trade
        trades_out.append({
            "date": day.isoformat(),
            "ticker": ticker,
            "entry_ts": pp.position.entry_ts.isoformat() if pp.position.entry_ts else None,
            "entry_px": pp.position.avg_entry,
            "exit_ts": ts.isoformat(),
            "exit_px": exit_px,
            "qty": qty,
            "pnl": pnl,
            "entry_reason": pp.position.entry_reason,
            "exit_reason": reason,
            "scaled": pp.position.scaled,
            "target1": pp.position.target1,
            "stop": pp.position.stop,
            "signal_ts": pp.position.signal_ts.isoformat() if pp.position.signal_ts else None,
            # Audit fields for position sizing verification
            "equity_at_entry": pp.position.equity_at_entry,
            "risk_dollars": pp.position.risk_dollars,
        })

        # Reset position
        pp.position = Position()

    def get_current_prices() -> dict[str, float]:
        """Get current prices for all tickers at the current timestamp."""
        prices = {}
        for ticker, df in ticker_bars.items():
            if current_ts in df.index:
                prices[ticker] = float(df.loc[current_ts, "c"])
        return prices

    # Main simulation loop - process all tickers at each timestamp
    for current_ts in sorted_timestamps:
        bar_time = current_ts.to_pydatetime().time()

        # Get current prices for all tickers
        current_prices = get_current_prices()

        # =================================================================
        # PHASE 1: Execute pending signals at this bar's OPEN
        # =================================================================
        for ticker, df in ticker_bars.items():
            if current_ts not in df.index:
                continue

            pp = portfolio.positions[ticker]
            row = df.loc[current_ts]
            o = float(row["o"])

            # Execute pending entry
            if pp.pending_entry is not None and not pp.position.is_open():
                # Check risk limits and capital
                can_trade, _ = portfolio.risk_state.can_trade(
                    current_ts.to_pydatetime(), max_trades_per_day, max_loss, cooldown_minutes
                )
                if can_trade and portfolio.can_open_position():
                    # Calculate position size based on risk
                    entry_px = fills.apply_entry(o)
                    stop_px = pp.pending_entry.stop_base * (1.0 - stop_buffer_pct)
                    stop_distance = abs(entry_px - stop_px)

                    if stop_distance > 0:
                        # Risk-based sizing: risk_amount / stop_distance
                        # CRITICAL FIX: Use current (mark-to-market) equity, not starting equity
                        current_equity = portfolio.get_equity(current_prices)
                        risk_amount = current_equity * risk_per_trade_pct
                        shares = risk_amount / stop_distance

                        # Apply capital constraints
                        max_value = portfolio.get_max_position_value(current_prices)
                        available = portfolio.get_available_capital(current_prices)
                        max_shares_capital = min(max_value, available) / entry_px

                        qty = min(shares, max_shares_capital)
                        qty = max(qty, 0)  # No negative quantities

                        # Apply starter fraction if applicable
                        if pp.pending_entry.ttm_state == "weak_bear" and allow_starter:
                            qty = qty * starter_frac

                        if qty > 0:
                            cost = entry_px * qty
                            portfolio.cash -= cost  # Deduct cost

                            record_fill(
                                ticker, current_ts, "BUY", qty, entry_px,
                                f"{pp.pending_entry.reason}|ttm={pp.pending_entry.ttm_state}",
                                signal_ts=pp.pending_entry.signal_ts,
                            )
                            pp.position.add(qty, entry_px)
                            pp.position.entry_ts = current_ts.to_pydatetime()
                            pp.position.signal_ts = pp.pending_entry.signal_ts
                            pp.position.entry_reason = f"{pp.pending_entry.reason}|ttm={pp.pending_entry.ttm_state}"
                            pp.position.stop = stop_px
                            pp.position.target1 = next_round_resistance(entry_px)
                            # Record equity and risk at entry for audit trail
                            pp.position.equity_at_entry = current_equity
                            pp.position.risk_dollars = risk_amount

                pp.pending_entry = None

            # Execute pending add-on
            if pp.pending_add is not None and pp.position.is_open():
                # Skip add-ons for now in portfolio mode (simplification)
                pp.pending_add = None

            # Execute pending exit
            if pp.pending_exit is not None and pp.position.is_open():
                if pp.pending_exit.limit_price is not None:
                    exit_px = fills.apply_exit(pp.pending_exit.limit_price)
                else:
                    exit_px = fills.apply_exit(o)
                close_position(ticker, pp, current_ts, exit_px, pp.pending_exit.reason,
                               signal_ts=pp.pending_exit.signal_ts)
                pp.pending_exit = None

        # =================================================================
        # PHASE 2: Handle intrabar events (stops, targets, force flat)
        # =================================================================
        for ticker, df in ticker_bars.items():
            if current_ts not in df.index:
                continue

            pp = portfolio.positions[ticker]
            row = df.loc[current_ts]
            c = float(row["c"])
            h = float(row["h"])
            l = float(row["l"])

            # Force flat at session end
            if pp.position.is_open() and force_flat_time is not None and bar_time >= force_flat_time:
                close_position(ticker, pp, current_ts, fills.apply_exit(c),
                               "force_flat_end_window", signal_ts=current_ts.to_pydatetime())
                continue

            # Update breakout seen
            pmh = row.get("pmh")
            if pd.notna(pmh) and c > float(pmh):
                pp.breakout_seen = True

            # Stop hit
            if pp.position.is_open() and pp.position.stop is not None and l <= pp.position.stop:
                exit_px = fills.apply_exit(pp.position.stop)
                close_position(ticker, pp, current_ts, exit_px, "stop_hit", signal_ts=pp.position.entry_ts)
                continue

            # Target hit - partial scale
            if pp.position.is_open() and (not pp.position.scaled) and pp.position.target1 is not None and h >= pp.position.target1:
                take_qty = pp.position.qty * scale_frac
                if take_qty > 0:
                    exit_px = fills.apply_exit(pp.position.target1)
                    record_fill(ticker, current_ts, "SELL", take_qty, exit_px,
                                "scale_out_target1", signal_ts=pp.position.entry_ts)
                    scale_pnl = (exit_px - pp.position.avg_entry) * take_qty - fills.fees_per_trade
                    # Subtract fees from cash to maintain ledger consistency with P&L
                    portfolio.cash += (exit_px * take_qty - fills.fees_per_trade)
                    portfolio.realized_pnl += scale_pnl
                    portfolio.risk_state.record_partial_pnl(scale_pnl)
                    pp.position.qty -= take_qty
                    pp.position.scaled = True
                    pp.position.stop = pp.position.avg_entry

        # =================================================================
        # PHASE 3: Evaluate conditions at bar CLOSE, create pending signals
        # =================================================================
        for ticker, df in ticker_bars.items():
            if current_ts not in df.index:
                continue

            pp = portfolio.positions[ticker]
            row = df.loc[current_ts]
            c = float(row["c"])

            # Helper to update prev values
            def update_prev():
                pp.prev_close = c
                pp.prev_vwap = float(row["vwap"]) if pd.notna(row.get("vwap")) else pp.prev_vwap
                pp.prev_ema21 = float(row["ema_21"]) if pd.notna(row.get("ema_21")) else pp.prev_ema21

            if not pp.position.is_open() and pp.pending_entry is None:
                # Check daily risk limits
                can_trade, _ = portfolio.risk_state.can_trade(
                    current_ts.to_pydatetime(), max_trades_per_day, max_loss, cooldown_minutes
                )
                if not can_trade:
                    update_prev()
                    continue

                # Check if we can open more positions
                if not portfolio.can_open_position():
                    update_prev()
                    continue

                # Macro filters
                if req_ema34 and not (c > float(row["ema_34"])):
                    update_prev()
                    continue
                if req_ema55 and not (c > float(row["ema_55"])):
                    update_prev()
                    continue
                if req_sma200:
                    sma200 = row.get("sma_200")
                    if pd.isna(sma200) or not (c > float(sma200)):
                        update_prev()
                        continue

                # Micro: above EMA21
                if not (c > float(row["ema_21"])):
                    update_prev()
                    continue

                ttm_state = row.get("ttm_state")
                if pd.isna(ttm_state):
                    update_prev()
                    continue

                is_starter = allow_starter and ttm_state == "weak_bear"
                ttm_ok = ttm_state in {"weak_bull", "strong_bull"} or is_starter
                if not ttm_ok:
                    update_prev()
                    continue

                if require_momo and row.get("momentum_sign") != "bull":
                    update_prev()
                    continue

                ext = row.get("extension_from_ema8_pct")
                if pd.notna(ext) and float(ext) > max_ext:
                    update_prev()
                    continue

                # Setup gating
                pmh = row.get("pmh")
                entry_reason: str | None = None
                if require_pmh_breakout:
                    if pd.isna(pmh):
                        update_prev()
                        continue
                    pmh_f = float(pmh)
                    crossed_pmh = pp.prev_close is not None and pp.prev_close <= pmh_f and c > pmh_f
                    if crossed_pmh:
                        entry_reason = "pmh_breakout"
                    else:
                        if pp.breakout_seen:
                            reclaimed_vwap = (
                                pp.prev_close is not None
                                and pp.prev_vwap is not None
                                and pp.prev_close <= pp.prev_vwap
                                and c > float(row["vwap"])
                            )
                            reclaimed_21 = (
                                pp.prev_close is not None
                                and pp.prev_ema21 is not None
                                and pp.prev_close <= pp.prev_ema21
                                and c > float(row["ema_21"])
                            )
                            if reclaimed_vwap:
                                entry_reason = "vwap_reclaim_after_pmh"
                            elif reclaimed_21:
                                entry_reason = "ema21_reclaim_after_pmh"
                        if entry_reason is None:
                            update_prev()
                            continue
                else:
                    entry_reason = "macro_micro_confirmed"

                # Calculate stop base
                if pd.notna(pmh) and c > float(pmh):
                    stop_base = float(pmh)
                else:
                    stop_base = min(float(row["ema_21"]), float(row["vwap"]))

                # Create pending entry
                pp.pending_entry = PendingEntry(
                    signal_ts=current_ts.to_pydatetime(),
                    qty=1.0,  # Will be calculated at fill time based on risk
                    reason=entry_reason,
                    ttm_state=str(ttm_state),
                    stop_base=stop_base,
                    pmh=float(pmh) if pd.notna(pmh) else None,
                )

            elif pp.position.is_open():
                # Exit signals
                if pp.pending_exit is None:
                    if exit_on_below_ema8 and c < float(row["ema_8"]):
                        pp.pending_exit = PendingExit(
                            signal_ts=current_ts.to_pydatetime(),
                            reason="close_below_ema8",
                            limit_price=None,
                        )
                    elif exit_on_ttm_momo_bear:
                        ttm_state = row.get("ttm_state")
                        if row.get("momentum_sign") == "bear" and ttm_state in {"weak_bear", "strong_bear"}:
                            pp.pending_exit = PendingExit(
                                signal_ts=current_ts.to_pydatetime(),
                                reason=f"ttm_momo_bear={ttm_state}",
                                limit_price=None,
                            )

            update_prev()

    # End of day: force flat all remaining positions
    if sorted_timestamps:
        last_ts = sorted_timestamps[-1]
        for ticker, pp in portfolio.positions.items():
            if pp.position.is_open() and ticker in ticker_bars:
                df = ticker_bars[ticker]
                if last_ts in df.index:
                    last_close = float(df.loc[last_ts, "c"])
                    close_position(ticker, pp, last_ts, fills.apply_exit(last_close),
                                   "force_flat_end_window", signal_ts=last_ts.to_pydatetime())

    return fills_out, trades_out, portfolio
