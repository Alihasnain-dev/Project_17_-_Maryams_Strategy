from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from ybi_strategy.config import Config
from ybi_strategy.features.indicators import compute_session_indicators, compute_trend_indicators
from ybi_strategy.polygon.client import PolygonClient
from ybi_strategy.backtest.fills import FillModel
from ybi_strategy.strategy.ybi_small_caps import simulate_ybi_small_caps
from ybi_strategy.timeutils import SessionTimes, parse_hhmm
from ybi_strategy.universe.watchlist import build_watchlist_open_gap


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
        self.fills = FillModel(model=slip_model, cents=cents)

    def run(self, *, start_date: str, end_date: str) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        days = pd.date_range(start=start_date, end=end_date, freq="D", tz=str(self.config.get("timezone")))
        all_trades: list[dict[str, Any]] = []
        all_fills: list[dict[str, Any]] = []
        all_watchlist: list[dict[str, Any]] = []

        for day_ts in days:
            if day_ts.dayofweek >= 5:
                continue
            d = day_ts.date()
            fills, trades, watchlist_rows = self._run_day(d)
            all_trades.extend(trades)
            all_fills.extend(fills)
            all_watchlist.extend(watchlist_rows)

        out_path = self.output_dir / "trades.csv"
        trades_df = pd.DataFrame(all_trades)
        trades_df.to_csv(out_path, index=False)
        fills_path = self.output_dir / "fills.csv"
        pd.DataFrame(all_fills).to_csv(fills_path, index=False)
        watchlist_path = self.output_dir / "watchlist.csv"
        pd.DataFrame(all_watchlist).to_csv(watchlist_path, index=False)

        summary_path = self.output_dir / "summary.json"
        summary = self._summarize(trades_df)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    def _summarize(self, trades_df: pd.DataFrame) -> dict[str, Any]:
        if trades_df.empty:
            return {"trades": 0}
        pnl = trades_df["pnl"].astype(float)
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        return {
            "trades": int(len(trades_df)),
            "win_rate": float((pnl > 0).mean()),
            "avg_pnl": float(pnl.mean()),
            "median_pnl": float(pnl.median()),
            "total_pnl": float(pnl.sum()),
            "avg_win": float(wins.mean()) if len(wins) else 0.0,
            "avg_loss": float(losses.mean()) if len(losses) else 0.0,
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

        trades: list[dict[str, Any]] = []
        fills: list[dict[str, Any]] = []
        watchlist_rows: list[dict[str, Any]] = [
            {"date": d.isoformat(), "ticker": i.ticker, "gap_pct": i.gap_pct, "prev_close": i.prev_close, "open_price": i.open_price}
            for i in wl
        ]
        for item in wl:
            bars = self.polygon.minute_bars(item.ticker, d)
            if not bars:
                continue

            df_full = self._bars_to_frame(bars)
            df_full = self._add_premarket_stats(df_full, d)
            df_full = compute_trend_indicators(df_full)
            df = self._filter_session(df_full, d)
            if df.empty:
                continue

            df = compute_session_indicators(df)
            fills_i, trades_i = simulate_ybi_small_caps(
                ticker=item.ticker,
                day=d,
                df=df,
                config=self.config,
                fills=self.fills,
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
        start = datetime(d.year, d.month, d.day, self.session.trade_start.hour, self.session.trade_start.minute, tzinfo=df.index.tz)
        end = datetime(d.year, d.month, d.day, self.session.trade_end.hour, self.session.trade_end.minute, tzinfo=df.index.tz)
        return df[(df.index >= start) & (df.index <= end)]

    def _add_premarket_stats(self, df: pd.DataFrame, d: date) -> pd.DataFrame:
        if df.empty:
            return df
        pm_start = datetime(d.year, d.month, d.day, self.premarket_start.hour, self.premarket_start.minute, tzinfo=df.index.tz)
        pm_end = datetime(d.year, d.month, d.day, self.premarket_end.hour, self.premarket_end.minute, tzinfo=df.index.tz)
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

    # Trades are simulated in `strategy/ybi_small_caps.py`.
