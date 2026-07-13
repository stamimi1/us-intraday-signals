"""Vectorized indicator helpers (hand-rolled: fewer deps, fast enough for replay)."""
import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR from open/high/low/close columns."""
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0):
    mid = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    return mid, mid + num_std * std, mid - num_std * std


def keltner(df: pd.DataFrame, window: int = 20, mult: float = 1.5):
    mid = ema(df["close"], window)
    rng = atr(df, window)
    return mid, mid + mult * rng, mid - mult * rng


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets each trading day (index must be tz-aware ET)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    day = df.index.date
    cum_pv = pv.groupby(day).cumsum()
    cum_vol = df["volume"].groupby(day).cumsum().replace(0, np.nan)
    return cum_pv / cum_vol


def vwap_band_sigma(df: pd.DataFrame, vwap: pd.Series) -> pd.Series:
    """Rolling per-session standard deviation of price around VWAP."""
    dev = df["close"] - vwap
    day = df.index.date
    # expanding std within each session; needs a few bars before it stabilizes
    return dev.groupby(day).expanding().std(ddof=0).reset_index(level=0, drop=True)
