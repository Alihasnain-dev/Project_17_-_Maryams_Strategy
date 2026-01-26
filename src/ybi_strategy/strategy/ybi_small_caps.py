from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import pandas as pd

from ybi_strategy.config import Config
from ybi_strategy.backtest.fills import FillModel


@dataclass
class Fill:
    date: str
    ticker: str
    ts: str
    side: str  # BUY | SELL
    qty: float
    price: float
    reason: str
    signal_ts: str | None = None  # Timestamp when signal was generated (for audit)


@dataclass
class PendingEntry:
    """
    A pending entry signal waiting to be filled on the next bar.

    This implements the "decide on bar close, fill on next bar open" pattern
    to eliminate lookahead bias.
    """
    signal_ts: datetime  # When the signal was generated (bar N close)
    qty: float
    reason: str
    ttm_state: str
    stop_base: float  # For stop calculation
    pmh: float | None = None  # Store PMH at signal time for stop calc


@dataclass
class PendingExit:
    """
    A pending exit signal waiting to be filled on the next bar.
    """
    signal_ts: datetime
    reason: str
    limit_price: float | None = None  # For target exits; None for market exits


@dataclass
class Position:
    qty: float = 0.0
    avg_entry: float = 0.0
    entry_ts: datetime | None = None
    entry_reason: str | None = None
    stop: float | None = None
    target1: float | None = None
    scaled: bool = False
    signal_ts: datetime | None = None  # When the entry signal was generated
    equity_at_entry: float = 0.0  # Mark-to-market equity at entry time (for audit)
    risk_dollars: float = 0.0  # Risk amount in dollars for this trade

    def is_open(self) -> bool:
        return self.qty > 0

    def add(self, qty: float, price: float) -> None:
        if qty <= 0:
            return
        new_qty = self.qty + qty
        if self.qty <= 0:
            self.avg_entry = price
        else:
            self.avg_entry = (self.avg_entry * self.qty + price * qty) / new_qty
        self.qty = new_qty


@dataclass
class DayRiskState:
    """
    Shared risk state across all tickers for a single day.

    This ensures daily risk limits (max trades, max loss, cooldown) are
    enforced globally, not per-ticker.
    """
    trade_count: int = 0
    realized_pnl: float = 0.0
    last_stop_ts: datetime | None = None

    def can_trade(
        self,
        current_ts: datetime,
        max_trades: int,
        max_loss: float,
        cooldown_minutes: int,
    ) -> tuple[bool, str]:
        """
        Check if we can take a new trade given current risk limits.

        Returns (can_trade, reason_if_blocked).
        """
        if self.trade_count >= max_trades:
            return False, "max_trades_reached"

        if self.realized_pnl <= -max_loss:
            return False, "max_daily_loss_reached"

        if self.last_stop_ts is not None:
            elapsed_mins = (current_ts - self.last_stop_ts).total_seconds() / 60
            if elapsed_mins < cooldown_minutes:
                return False, "cooldown_active"

        return True, ""

    def record_entry(self) -> None:
        """
        Record a new trade ENTRY.

        CRITICAL: Trade count must be incremented at ENTRY time, not exit time.
        This prevents opening more than max_trades concurrent positions before
        any of them close.
        """
        self.trade_count += 1

    def record_exit(self, pnl: float, was_stop: bool, exit_ts: datetime) -> None:
        """
        Record a trade EXIT (close).

        NOTE: Trade count is NOT incremented here - it was already counted at entry.
        This method only records P&L and cooldown state.
        """
        self.realized_pnl += pnl
        if was_stop:
            self.last_stop_ts = exit_ts

    def record_trade(self, pnl: float, was_stop: bool, exit_ts: datetime) -> None:
        """
        DEPRECATED: Use record_entry() at entry and record_exit() at exit.

        This method is kept for backwards compatibility with legacy code paths
        that open and close in the same call. It increments trade_count, which
        is WRONG for portfolio mode with concurrent positions.
        """
        self.trade_count += 1
        self.realized_pnl += pnl
        if was_stop:
            self.last_stop_ts = exit_ts

    def record_partial_pnl(self, pnl: float) -> None:
        """Record P&L from a partial scale (doesn't count as a trade)."""
        self.realized_pnl += pnl


def _round_step(price: float) -> float:
    if price < 1:
        return 0.05
    if price < 5:
        return 0.10
    if price < 10:
        return 0.25
    return 0.50


def next_round_resistance(price: float) -> float:
    step = _round_step(price)
    mult = int(price / step) + 1
    return round(mult * step, 4)


def simulate_ybi_small_caps(
    *,
    ticker: str,
    day: date,
    df: pd.DataFrame,
    config: Config,
    fills: FillModel,
    max_trades_per_day: int = 5,
    max_daily_loss_pct: float = 0.02,
    cooldown_minutes: int = 2,
    account_equity: float = 10000.0,
    force_flat_time: time | None = None,
    day_risk_state: DayRiskState | None = None,
) -> tuple[list[Fill], list[dict[str, Any]]]:
    """
    A conservative, causal trade simulator for the YBI small-caps concept.

    Implements (MVP+):
    - Setup A: PMH breakout gate (optional)
    - Setup B: "failed breakdown" reclaim of VWAP or EMA21 after PMH is in play
    - Starter entries when TTM is weak_bear (optional) + add-to-full when flips bull
    - Partial scale-out (50%) at a simple derived resistance (next round level)
    - Exits: stop, close below EMA8, and/or TTM+momentum bear flip
    """
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

    fills_out: list[Fill] = []
    trades_out: list[dict[str, Any]] = []

    pos = Position()
    realized_pnl = 0.0
    breakout_seen = False

    # Use shared day risk state if provided, otherwise create local state
    # (local state maintains backward compatibility but doesn't enforce daily limits across tickers)
    risk_state = day_risk_state if day_risk_state is not None else DayRiskState()
    max_loss = account_equity * max_daily_loss_pct

    prev_close: float | None = None
    prev_vwap: float | None = None
    prev_ema21: float | None = None

    def record_fill(
        ts: pd.Timestamp,
        side: str,
        qty: float,
        px: float,
        reason: str,
        signal_ts: datetime | None = None,
    ) -> None:
        fills_out.append(
            Fill(
                date=day.isoformat(),
                ticker=ticker,
                ts=ts.isoformat(),
                side=side,
                qty=qty,
                price=px,
                reason=reason,
                signal_ts=signal_ts.isoformat() if signal_ts else None,
            )
        )

    def close_position(
        ts: pd.Timestamp,
        exit_px: float,
        reason: str,
        signal_ts: datetime | None = None,
    ) -> None:
        nonlocal realized_pnl, pos
        if not pos.is_open():
            return
        qty = pos.qty
        record_fill(ts, "SELL", qty, exit_px, reason, signal_ts=signal_ts)
        pnl = (exit_px - pos.avg_entry) * qty - fills.fees_per_trade
        realized_pnl += pnl
        # Update shared risk state
        risk_state.record_trade(pnl, was_stop=(reason == "stop_hit"), exit_ts=ts.to_pydatetime())
        trades_out.append(
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "entry_ts": pos.entry_ts.isoformat() if pos.entry_ts else None,
                "entry_px": pos.avg_entry,
                "exit_ts": ts.isoformat(),
                "exit_px": exit_px,
                "qty": qty,
                "pnl": pnl,
                "entry_reason": pos.entry_reason,
                "exit_reason": reason,
                "scaled": pos.scaled,
                "target1": pos.target1,
                "stop": pos.stop,
                "signal_ts": pos.signal_ts.isoformat() if pos.signal_ts else None,
            }
        )
        pos = Position()

    # Pending signals for next-bar execution (eliminates lookahead bias)
    pending_entry: PendingEntry | None = None
    pending_exit: PendingExit | None = None
    pending_add: PendingEntry | None = None  # For starter add-on signals

    # Helper to update prev values
    def update_prev_values(row: pd.Series) -> None:
        nonlocal prev_close, prev_vwap, prev_ema21
        prev_close = float(row["c"])
        prev_vwap = float(row["vwap"]) if pd.notna(row.get("vwap")) else prev_vwap
        prev_ema21 = float(row["ema_21"]) if pd.notna(row.get("ema_21")) else prev_ema21

    for i, (ts, row) in enumerate(df.iterrows()):
        o = float(row["o"])  # Open price for fills
        c = float(row["c"])
        h = float(row["h"])
        l = float(row["l"])
        bar_time = ts.to_pydatetime().time()

        # =================================================================
        # PHASE 1: Execute pending signals at this bar's OPEN
        # This implements "decide on bar N close, fill on bar N+1 open"
        # =================================================================

        # Execute pending entry at this bar's open
        if pending_entry is not None and not pos.is_open():
            # Check daily risk limits at execution time
            can_trade, block_reason = risk_state.can_trade(
                current_ts=ts.to_pydatetime(),
                max_trades=max_trades_per_day,
                max_loss=max_loss,
                cooldown_minutes=cooldown_minutes,
            )
            if can_trade:
                entry_px = fills.apply_entry(o)
                record_fill(
                    ts, "BUY", pending_entry.qty, entry_px,
                    f"{pending_entry.reason}|ttm={pending_entry.ttm_state}",
                    signal_ts=pending_entry.signal_ts,
                )
                pos.add(pending_entry.qty, entry_px)
                pos.entry_ts = ts.to_pydatetime()
                pos.signal_ts = pending_entry.signal_ts
                pos.entry_reason = f"{pending_entry.reason}|ttm={pending_entry.ttm_state}"

                # Stop/target initialization using signal-time values
                pos.stop = pending_entry.stop_base * (1.0 - stop_buffer_pct)
                pos.target1 = next_round_resistance(entry_px)

            pending_entry = None

        # Execute pending add-on at this bar's open
        if pending_add is not None and pos.is_open() and pos.qty < 1.0:
            add_px = fills.apply_entry(o)
            add_qty = pending_add.qty
            record_fill(
                ts, "BUY", add_qty, add_px,
                "starter_add_on_bull_flip",
                signal_ts=pending_add.signal_ts,
            )
            pos.add(add_qty, add_px)
            pending_add = None

        # Execute pending exit at this bar's open
        if pending_exit is not None and pos.is_open():
            if pending_exit.limit_price is not None:
                exit_px = fills.apply_exit(pending_exit.limit_price)
            else:
                exit_px = fills.apply_exit(o)
            close_position(ts, exit_px, pending_exit.reason, signal_ts=pending_exit.signal_ts)
            pending_exit = None
            update_prev_values(row)
            continue

        # =================================================================
        # PHASE 2: Handle intrabar events (stops, targets, force flat)
        # These CAN execute within the bar since they're price-triggered
        # =================================================================

        # Force flat at session end (immediate execution)
        if pos.is_open() and force_flat_time is not None and bar_time >= force_flat_time:
            close_position(ts, fills.apply_exit(c), "force_flat_end_window", signal_ts=ts.to_pydatetime())
            update_prev_values(row)
            continue

        pmh = row.get("pmh")
        if pd.notna(pmh) and c > float(pmh):
            breakout_seen = True

        # Intrabar stop handling: stop triggers if low breaches stop level
        # This is legitimate - stops are price-triggered orders
        if pos.is_open() and pos.stop is not None and l <= pos.stop:
            exit_px = fills.apply_exit(pos.stop)
            close_position(ts, exit_px, "stop_hit", signal_ts=pos.entry_ts)
            update_prev_values(row)
            continue

        # Intrabar target handling: target triggers if high reaches target
        # Partial scale at target is also price-triggered
        if pos.is_open() and (not pos.scaled) and pos.target1 is not None and h >= pos.target1:
            take_qty = pos.qty * scale_frac
            if take_qty > 0:
                exit_px = fills.apply_exit(pos.target1)
                record_fill(ts, "SELL", take_qty, exit_px, "scale_out_target1", signal_ts=pos.entry_ts)
                scale_pnl = (exit_px - pos.avg_entry) * take_qty - fills.fees_per_trade
                realized_pnl += scale_pnl
                risk_state.record_partial_pnl(scale_pnl)
                pos.qty -= take_qty
                pos.scaled = True
                pos.stop = pos.avg_entry  # move stop to breakeven after first partial

        # =================================================================
        # PHASE 3: Evaluate conditions at bar CLOSE, create pending signals
        # Signals generated here will execute at NEXT bar's open
        # =================================================================

        if not pos.is_open() and pending_entry is None:
            # Check daily risk limits before generating signal
            can_trade, block_reason = risk_state.can_trade(
                current_ts=ts.to_pydatetime(),
                max_trades=max_trades_per_day,
                max_loss=max_loss,
                cooldown_minutes=cooldown_minutes,
            )
            if not can_trade:
                update_prev_values(row)
                continue

            # Macro regime filters
            if req_ema34 and not (c > float(row["ema_34"])):
                update_prev_values(row)
                continue
            if req_ema55 and not (c > float(row["ema_55"])):
                update_prev_values(row)
                continue
            if req_sma200:
                sma200 = row.get("sma_200")
                if pd.isna(sma200) or not (c > float(sma200)):
                    update_prev_values(row)
                    continue

            # Micro: above EMA21
            if not (c > float(row["ema_21"])):
                update_prev_values(row)
                continue

            ttm_state = row.get("ttm_state")
            if pd.isna(ttm_state):
                update_prev_values(row)
                continue

            is_starter = allow_starter and ttm_state == "weak_bear"
            ttm_ok = ttm_state in {"weak_bull", "strong_bull"} or is_starter
            if not ttm_ok:
                update_prev_values(row)
                continue

            if require_momo and row.get("momentum_sign") != "bull":
                update_prev_values(row)
                continue

            ext = row.get("extension_from_ema8_pct")
            if pd.notna(ext) and float(ext) > max_ext:
                update_prev_values(row)
                continue

            # Setup gating
            entry_reason: str | None = None
            if require_pmh_breakout:
                if pd.isna(pmh):
                    update_prev_values(row)
                    continue
                pmh_f = float(pmh)
                crossed_pmh = prev_close is not None and prev_close <= pmh_f and c > pmh_f
                if crossed_pmh:
                    entry_reason = "pmh_breakout"
                else:
                    if breakout_seen:
                        reclaimed_vwap = (
                            prev_close is not None
                            and prev_vwap is not None
                            and prev_close <= prev_vwap
                            and c > float(row["vwap"])
                        )
                        reclaimed_21 = (
                            prev_close is not None
                            and prev_ema21 is not None
                            and prev_close <= prev_ema21
                            and c > float(row["ema_21"])
                        )
                        if reclaimed_vwap:
                            entry_reason = "vwap_reclaim_after_pmh"
                        elif reclaimed_21:
                            entry_reason = "ema21_reclaim_after_pmh"
                    if entry_reason is None:
                        update_prev_values(row)
                        continue
            else:
                entry_reason = "macro_micro_confirmed"

            # Calculate stop base at signal time (stored for use at fill time)
            if pd.notna(pmh) and c > float(pmh):
                stop_base = float(pmh)
            else:
                stop_base = min(float(row["ema_21"]), float(row["vwap"]))

            qty = starter_frac if is_starter else 1.0

            # CREATE PENDING ENTRY (will execute at next bar's open)
            pending_entry = PendingEntry(
                signal_ts=ts.to_pydatetime(),
                qty=qty,
                reason=entry_reason,
                ttm_state=str(ttm_state),
                stop_base=stop_base,
                pmh=float(pmh) if pd.notna(pmh) else None,
            )

        elif pos.is_open():
            # Add-to-full-size logic for starter entries
            if allow_starter and pos.qty < 1.0 and pending_add is None:
                ttm_state = row.get("ttm_state")
                if (
                    row.get("momentum_sign") == "bull"
                    and ttm_state in {"weak_bull", "strong_bull"}
                    and c > float(row["ema_21"])
                    and c > float(row["vwap"])
                ):
                    add_qty = 1.0 - pos.qty
                    # CREATE PENDING ADD (will execute at next bar's open)
                    pending_add = PendingEntry(
                        signal_ts=ts.to_pydatetime(),
                        qty=add_qty,
                        reason="starter_add_on_bull_flip",
                        ttm_state=str(ttm_state),
                        stop_base=0.0,  # Not used for adds
                    )

            # Indicator-based exit signals (at close) -> execute at next bar open
            if pending_exit is None:
                if exit_on_below_ema8 and c < float(row["ema_8"]):
                    pending_exit = PendingExit(
                        signal_ts=ts.to_pydatetime(),
                        reason="close_below_ema8",
                        limit_price=None,  # Market order at next open
                    )
                elif exit_on_ttm_momo_bear:
                    ttm_state = row.get("ttm_state")
                    if row.get("momentum_sign") == "bear" and ttm_state in {"weak_bear", "strong_bear"}:
                        pending_exit = PendingExit(
                            signal_ts=ts.to_pydatetime(),
                            reason=f"ttm_momo_bear={ttm_state}",
                            limit_price=None,
                        )

        update_prev_values(row)

    # =================================================================
    # End of day: Cancel pending signals and force flat
    # =================================================================

    # Cancel any pending entry that didn't get filled (no more bars)
    if pending_entry is not None:
        pending_entry = None  # Signal expires

    # Force flat at end of dataframe
    if pos.is_open():
        last_ts = df.index[-1]
        last_close = float(df.iloc[-1]["c"])
        close_position(last_ts, fills.apply_exit(last_close), "force_flat_end_window", signal_ts=last_ts.to_pydatetime())

    return fills_out, trades_out
