from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from ybi_strategy.polygon.client import PolygonClient


@dataclass(frozen=True)
class WatchlistItem:
    ticker: str
    gap_pct: float
    prev_close: float
    open_price: float


def _to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Polygon grouped daily fields are typically:
    # T=ticker, o=open, c=close, h=high, l=low, v=volume, vw=vwap, n=transactions, t=timestamp(ms)
    return df


def build_watchlist_open_gap(
    *,
    polygon: PolygonClient,
    day: date,
    top_n: int,
    min_gap_pct: float,
    min_prev_close: float,
    max_prev_close: float,
) -> list[WatchlistItem]:
    prev: list[dict[str, Any]] = []
    prev_day = day - timedelta(days=1)
    for _ in range(7):
        prev = polygon.grouped_daily(prev_day)
        if prev:
            break
        prev_day = prev_day - timedelta(days=1)
    if not prev:
        return []
    cur = polygon.grouped_daily(day)
    if not cur:
        return []

    prev_df = _to_frame(prev)[["T", "c"]].rename(columns={"T": "ticker", "c": "prev_close"})
    cur_df = _to_frame(cur)[["T", "o"]].rename(columns={"T": "ticker", "o": "open_price"})

    merged = cur_df.merge(prev_df, on="ticker", how="inner")
    merged = merged[(merged["open_price"] > 0) & (merged["prev_close"] > 0)]
    merged = merged[(merged["prev_close"] >= min_prev_close) & (merged["prev_close"] <= max_prev_close)]
    merged["gap_pct"] = (merged["open_price"] / merged["prev_close"]) - 1.0
    merged = merged[merged["gap_pct"] >= min_gap_pct]

    merged = merged.sort_values("gap_pct", ascending=False).head(int(top_n))
    items: list[WatchlistItem] = []
    for _, row in merged.iterrows():
        items.append(
            WatchlistItem(
                ticker=str(row["ticker"]),
                gap_pct=float(row["gap_pct"]),
                prev_close=float(row["prev_close"]),
                open_price=float(row["open_price"]),
            )
        )
    return items
