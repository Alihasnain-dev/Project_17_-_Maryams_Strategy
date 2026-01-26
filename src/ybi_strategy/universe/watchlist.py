from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from ybi_strategy.polygon.client import PolygonClient


# =============================================================================
# COMMON STOCK FILTER
# =============================================================================
# Pattern-based exclusion rules for non-common-stock tickers.
# These are applied as a backstop in addition to Polygon reference data.
#
# Known patterns to exclude:
# - .WS suffix: Warrants (e.g., QBTS.WS)
# - W suffix after 4+ letters: Warrants (e.g., SOUNW, AFRM.W)
# - .U suffix: Units (e.g., AFRM.U)
# - .R suffix: Rights
# - ^ prefix: Index or special symbols
# - Test/placeholder tickers (ZVZZT, etc.)
# =============================================================================

# =============================================================================
# PATTERN CATEGORIES
# =============================================================================
# UNAMBIGUOUS patterns: These are safe to apply always (explicit suffixes)
UNAMBIGUOUS_NON_COMMON_PATTERNS = [
    r"\.WS$",       # Warrants (explicit .WS suffix, e.g., QBTS.WS)
    r"\.W$",        # Warrants (explicit .W suffix, e.g., AFRM.W)
    r"\.U$",        # Units (e.g., SPAC.U)
    r"\.R$",        # Rights
    r"\^",          # Index or special symbols (e.g., ^SPX)
]

# AMBIGUOUS patterns: These can cause FALSE POSITIVES on legitimate stocks
# Examples of legitimate stocks that would be incorrectly filtered:
#   - SNOW, LKNW, BMW (W suffix) - but these are common stocks
#   - SHOP, TRIP, COUP (P suffix) - legitimate common stocks
# These should ONLY be used when reference data is NOT available
AMBIGUOUS_NON_COMMON_PATTERNS = [
    r"W$",          # Warrants (W suffix after 4+ chars) - CAN HAVE FALSE POSITIVES
    r"P$",          # Preferreds (P suffix after 3+ chars) - CAN HAVE FALSE POSITIVES
]

# Test/placeholder tickers to exclude
TEST_TICKERS = {"ZVZZT", "ZVZZC", "ZTEST", "TEST"}


def is_common_stock_ticker(ticker: str, use_ambiguous_patterns: bool = True) -> bool:
    """
    Check if a ticker appears to be a common stock based on pattern rules.

    IMPORTANT: This is a heuristic filter. For definitive classification,
    use Polygon reference data (type == "CS", active, not OTC).

    Args:
        ticker: The ticker symbol to check.
        use_ambiguous_patterns: If True (default), apply W$ and P$ patterns which
            can cause false positives on legitimate stocks like SNOW, SHOP.
            Set to False when reference data will be used for verification.

    Returns:
        True if the ticker appears to be a common stock, False otherwise.
    """
    if not ticker or not isinstance(ticker, str):
        return False

    ticker_upper = ticker.upper().strip()

    # Exclude test tickers
    if ticker_upper in TEST_TICKERS:
        return False

    # Always apply unambiguous patterns (explicit suffixes like .WS, .U, .R)
    for pattern in UNAMBIGUOUS_NON_COMMON_PATTERNS:
        if re.search(pattern, ticker_upper):
            return False

    # Only apply ambiguous patterns if explicitly requested
    # These patterns (W$, P$) can cause FALSE POSITIVES on legitimate stocks
    if use_ambiguous_patterns:
        for pattern in AMBIGUOUS_NON_COMMON_PATTERNS:
            if re.search(pattern, ticker_upper):
                # Special case: W suffix only applies to tickers with 4+ chars total
                if pattern == r"W$":
                    # Allow short tickers ending in W (e.g., "W" itself, "VW", "BMW")
                    if len(ticker_upper) <= 3:
                        continue
                    # Check if the base (without W) is at least 3 chars
                    base = ticker_upper[:-1]
                    if len(base) < 3:
                        continue
                # Special case: P suffix only applies to tickers with 4+ chars total
                if pattern == r"P$":
                    # Allow short tickers ending in P (e.g., "P", "UP", "APP")
                    if len(ticker_upper) <= 3:
                        continue
                    base = ticker_upper[:-1]
                    if len(base) < 3:
                        continue
                return False

    # Basic format check: only alphanumeric and dots, 1-10 chars
    if not re.match(r"^[A-Z0-9\.]{1,10}$", ticker_upper):
        return False

    return True


def filter_common_stocks(
    tickers: list[str],
    polygon: PolygonClient | None = None,
    use_reference_data: bool = True,
) -> list[str]:
    """
    Filter a list of tickers to only include common stocks.

    IMPORTANT: When use_reference_data=True, this function does NOT apply
    ambiguous pattern rules (W$, P$) because they cause false positives.
    Instead, it relies on Polygon reference data for definitive classification.

    Args:
        tickers: List of ticker symbols to filter.
        polygon: Optional PolygonClient for reference data lookup.
        use_reference_data: Whether to use Polygon reference data (recommended).

    Returns:
        List of tickers that are classified as common stocks.
    """
    common_stocks = []

    # When reference data is available, don't use ambiguous patterns (W$, P$)
    # to avoid false positives on legitimate stocks like SNOW, SHOP
    use_ambiguous = not (use_reference_data and polygon is not None)

    for ticker in tickers:
        # Apply pattern-based filter
        # CRITICAL: Skip ambiguous patterns when reference data will verify
        if not is_common_stock_ticker(ticker, use_ambiguous_patterns=use_ambiguous):
            continue

        # When reference data is enabled, use Polygon for definitive classification
        if use_reference_data and polygon is not None:
            details = polygon.ticker_details(ticker)
            if details:
                # Check asset type - ONLY allow common stocks (CS)
                ticker_type = details.get("type", "")
                market = details.get("market", "")

                # Exclude: WARRANT, ETF, ETN, FUND, UNIT, RIGHT, ADR, PFD, etc.
                if ticker_type != "CS":
                    continue

                # Exclude OTC markets
                if market.lower() == "otc":
                    continue

                # Exclude inactive tickers
                if not details.get("active", True):
                    continue
            else:
                # No reference data available - skip this ticker to be safe
                # (could also use ambiguous patterns here as fallback)
                continue

        common_stocks.append(ticker)

    return common_stocks


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
    filter_common_stocks_only: bool = True,
    use_reference_data: bool = True,  # CRITICAL: Default True - pattern filter alone misses preferreds (e.g., CCLDP)
) -> list[WatchlistItem]:
    """
    Build watchlist of small-cap stocks with gap-up on market open.

    Args:
        polygon: PolygonClient for market data.
        day: Trading day to build watchlist for.
        top_n: Maximum number of stocks to include.
        min_gap_pct: Minimum gap percentage (e.g., 0.05 = 5%).
        min_prev_close: Minimum previous day close price.
        max_prev_close: Maximum previous day close price.
        filter_common_stocks_only: If True, exclude warrants/units/OTC.
        use_reference_data: If True (default), verify with Polygon reference data.
            This is REQUIRED to filter out preferreds (e.g., CCLDP) and other non-CS
            instruments that pattern rules miss. Only set False for testing.

    Returns:
        List of WatchlistItem sorted by gap percentage descending.
    """
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

    # CRITICAL: Filter to common stocks only (exclude warrants, units, OTC, preferreds)
    if filter_common_stocks_only:
        # Use filter_common_stocks which handles reference data properly
        # When use_reference_data=True, it skips ambiguous patterns (W$, P$)
        # to avoid false positives on legitimate stocks
        verified_tickers = filter_common_stocks(
            merged["ticker"].tolist(),
            polygon=polygon,
            use_reference_data=use_reference_data,
        )
        merged = merged[merged["ticker"].isin(verified_tickers)]

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
