from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def vwap(typical_price: pd.Series, volume: pd.Series) -> pd.Series:
    # Causal, cumulative VWAP.
    pv = typical_price * volume
    cum_pv = pv.cumsum()
    cum_v = volume.cumsum().replace(0, np.nan)
    return (cum_pv / cum_v).ffill()


def atr(df: pd.DataFrame, window: int) -> pd.Series:
    prev_close = df["c"].shift(1)
    tr = pd.concat(
        [
            (df["h"] - df["l"]).abs(),
            (df["h"] - prev_close).abs(),
            (df["l"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=window, min_periods=window).mean()


def _linreg_last(y: np.ndarray) -> float:
    x = np.arange(len(y), dtype=float)
    if np.all(np.isnan(y)):
        return float("nan")
    y = np.nan_to_num(y, nan=0.0)
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope * x[-1] + intercept)


def ttm_squeeze_proxy(
    df: pd.DataFrame,
    *,
    length: int = 20,
    bb_mult: float = 2.0,
    kc_mult: float = 1.5,
) -> pd.DataFrame:
    """
    Approximate TTM Squeeze components:
    - Bollinger Bands (SMA +/- bb_mult*STD)
    - Keltner Channels (EMA +/- kc_mult*ATR)
    - "Squeeze on" when BB is inside KC

    Momentum proxy uses a common LazyBear-style construction, then applies a rolling
    linear regression to form a histogram-like series.
    """
    out = df.copy()
    sma_mid = out["c"].rolling(window=length, min_periods=length).mean()
    std = out["c"].rolling(window=length, min_periods=length).std(ddof=0)
    bb_upper = sma_mid + bb_mult * std
    bb_lower = sma_mid - bb_mult * std

    ema_mid = ema(out["c"], length)
    atr_val = atr(out, window=length)
    kc_upper = ema_mid + kc_mult * atr_val
    kc_lower = ema_mid - kc_mult * atr_val

    squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

    highest_high = out["h"].rolling(window=length, min_periods=length).max()
    lowest_low = out["l"].rolling(window=length, min_periods=length).min()
    m1 = (highest_high + lowest_low) / 2.0
    m2 = (m1 + sma_mid) / 2.0
    momentum_raw = out["c"] - m2
    momentum = momentum_raw.rolling(window=length, min_periods=length).apply(
        lambda w: _linreg_last(np.asarray(w, dtype=float)),
        raw=False,
    )

    out["ttm_bb_upper"] = bb_upper
    out["ttm_bb_lower"] = bb_lower
    out["ttm_kc_upper"] = kc_upper
    out["ttm_kc_lower"] = kc_lower
    out["ttm_squeeze_on"] = squeeze_on
    out["momentum"] = momentum
    return out


def ttm_color_state(momentum: pd.Series) -> pd.Series:
    delta = momentum.diff()
    state = pd.Series(index=momentum.index, dtype="object")
    state[(momentum > 0) & (delta >= 0)] = "strong_bull"
    state[(momentum > 0) & (delta < 0)] = "weak_bull"
    state[(momentum < 0) & (delta < 0)] = "strong_bear"
    state[(momentum < 0) & (delta >= 0)] = "weak_bear"
    return state


def compute_intraday_levels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hod_so_far"] = out["h"].cummax()
    out["lod_so_far"] = out["l"].cummin()
    return out


def compute_trend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Trend + momentum indicators that can be computed on a broader window (e.g. include premarket)
    to avoid "cold start" during the open.
    """
    out = df.copy()
    out["ema_8"] = ema(out["c"], 8)
    out["ema_21"] = ema(out["c"], 21)
    out["ema_34"] = ema(out["c"], 34)
    out["ema_55"] = ema(out["c"], 55)
    out["sma_200"] = sma(out["c"], 200)
    out = ttm_squeeze_proxy(out)
    out["ttm_state"] = ttm_color_state(out["momentum"])
    out["momentum_sign"] = np.where(out["momentum"] >= 0, "bull", "bear")
    out = compute_intraday_levels(out)
    return out


def compute_session_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Session-only indicators (e.g., RTH VWAP). Intended to be called after slicing to the
    trading window.
    """
    out = df.copy()
    typical = (out["h"] + out["l"] + out["c"]) / 3.0
    out["vwap"] = vwap(typical, out["v"])
    out["extension_from_ema8_pct"] = (out["h"] - out["ema_8"]) / out["ema_8"]
    return out


def compute_core_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience wrapper: computes both trend and session indicators on the same dataframe.
    Prefer `compute_trend_indicators` on a broader window + `compute_session_indicators` on
    the trading slice for more realistic open behavior.
    """
    out = compute_trend_indicators(df)
    out = compute_session_indicators(out)
    return out
