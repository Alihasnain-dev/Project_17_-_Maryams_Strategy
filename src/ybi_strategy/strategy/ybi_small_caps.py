from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass
class Position:
    qty: float = 0.0
    avg_entry: float = 0.0
    entry_ts: datetime | None = None
    entry_reason: str | None = None
    stop: float | None = None
    target1: float | None = None
    scaled: bool = False

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

    prev_close: float | None = None
    prev_vwap: float | None = None
    prev_ema21: float | None = None

    def record_fill(ts: pd.Timestamp, side: str, qty: float, px: float, reason: str) -> None:
        fills_out.append(
            Fill(
                date=day.isoformat(),
                ticker=ticker,
                ts=ts.isoformat(),
                side=side,
                qty=qty,
                price=px,
                reason=reason,
            )
        )

    def close_position(ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal realized_pnl, pos
        if not pos.is_open():
            return
        qty = pos.qty
        record_fill(ts, "SELL", qty, exit_px, reason)
        pnl = (exit_px - pos.avg_entry) * qty
        realized_pnl += pnl
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
            }
        )
        pos = Position()

    for ts, row in df.iterrows():
        c = float(row["c"])
        h = float(row["h"])
        l = float(row["l"])

        pmh = row.get("pmh")
        if pd.notna(pmh) and c > float(pmh):
            breakout_seen = True

        # Intrabar stop handling (conservative: stop triggers before target if both in same bar).
        if pos.is_open() and pos.stop is not None and l <= pos.stop:
            exit_px = fills.apply_exit(pos.stop)
            close_position(ts, exit_px, "stop_hit")
            prev_close = c
            continue

        if pos.is_open() and (not pos.scaled) and pos.target1 is not None and h >= pos.target1:
            take_qty = pos.qty * scale_frac
            if take_qty > 0:
                exit_px = fills.apply_exit(pos.target1)
                record_fill(ts, "SELL", take_qty, exit_px, "scale_out_target1")
                realized_pnl += (exit_px - pos.avg_entry) * take_qty
                pos.qty -= take_qty
                pos.scaled = True
                pos.stop = pos.avg_entry  # move stop to breakeven after first partial

        if not pos.is_open():
            # Macro regime filters.
            if req_ema34 and not (c > float(row["ema_34"])):
                prev_close = c
                continue
            if req_ema55 and not (c > float(row["ema_55"])):
                prev_close = c
                continue
            if req_sma200:
                sma200 = row.get("sma_200")
                if pd.isna(sma200) or not (c > float(sma200)):
                    prev_close = c
                    continue

            # Micro: above EMA21.
            if not (c > float(row["ema_21"])):
                prev_close = c
                continue

            ttm_state = row.get("ttm_state")
            if pd.isna(ttm_state):
                prev_close = c
                continue

            is_starter = allow_starter and ttm_state == "weak_bear"
            ttm_ok = ttm_state in {"weak_bull", "strong_bull"} or is_starter
            if not ttm_ok:
                prev_close = c
                continue

            if require_momo and row.get("momentum_sign") != "bull":
                prev_close = c
                continue

            ext = row.get("extension_from_ema8_pct")
            if pd.notna(ext) and float(ext) > max_ext:
                prev_close = c
                continue

            # Setup gating:
            # - If configured, require a PMH breakout trigger OR (after breakout seen) a reclaim of VWAP/EMA21.
            entry_reason: str | None = None
            if require_pmh_breakout:
                if pd.isna(pmh):
                    prev_close = c
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
                        prev_close = c
                        prev_vwap = float(row["vwap"]) if pd.notna(row.get("vwap")) else prev_vwap
                        prev_ema21 = float(row["ema_21"]) if pd.notna(row.get("ema_21")) else prev_ema21
                        continue
            else:
                entry_reason = "macro_micro_confirmed"

            qty = starter_frac if is_starter else 1.0
            entry_px = fills.apply_entry(c)
            record_fill(ts, "BUY", qty, entry_px, f"{entry_reason}|ttm={ttm_state}")
            pos.add(qty, entry_px)
            pos.entry_ts = ts.to_pydatetime()
            pos.entry_reason = f"{entry_reason}|ttm={ttm_state}"

            # Stop/target initialization.
            if pd.notna(pmh) and c > float(pmh):
                stop_base = float(pmh)
            else:
                stop_base = min(float(row["ema_21"]), float(row["vwap"]))
            pos.stop = stop_base * (1.0 - stop_buffer_pct)
            pos.target1 = next_round_resistance(entry_px)

        else:
            # Add-to-full-size logic for starter entries.
            if allow_starter and pos.qty < 1.0:
                ttm_state = row.get("ttm_state")
                if row.get("momentum_sign") == "bull" and ttm_state in {"weak_bull", "strong_bull"} and c > float(row["ema_21"]) and c > float(row["vwap"]):
                    add_qty = 1.0 - pos.qty
                    add_px = fills.apply_entry(c)
                    record_fill(ts, "BUY", add_qty, add_px, "starter_add_on_bull_flip")
                    pos.add(add_qty, add_px)

            # Indicator-based exits (at close).
            if exit_on_below_ema8 and c < float(row["ema_8"]):
                close_position(ts, fills.apply_exit(c), "close_below_ema8")
                prev_close = c
                continue

            if exit_on_ttm_momo_bear:
                ttm_state = row.get("ttm_state")
                if row.get("momentum_sign") == "bear" and ttm_state in {"weak_bear", "strong_bear"}:
                    close_position(ts, fills.apply_exit(c), f"ttm_momo_bear={ttm_state}")
                    prev_close = c
                    continue

        prev_close = c
        prev_vwap = float(row["vwap"]) if pd.notna(row.get("vwap")) else prev_vwap
        prev_ema21 = float(row["ema_21"]) if pd.notna(row.get("ema_21")) else prev_ema21

    # Force flat at end of dataframe.
    if pos.is_open():
        last_ts = df.index[-1]
        last_close = float(df.iloc[-1]["c"])
        close_position(last_ts, fills.apply_exit(last_close), "force_flat_end_window")

    return fills_out, trades_out
