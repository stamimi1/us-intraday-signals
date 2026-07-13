"""
Batched intraday data via yfinance. One download per interval covers the whole
universe (a single HTTP request for ~40 tickers), which keeps a 1-minute
engine cadence well inside Yahoo's tolerance.

All frames: columns open/high/low/close/volume, tz-aware America/New_York
index, regular session only (09:30-16:00), incomplete last bar dropped.
"""
import logging
from datetime import datetime, time as dtime, timedelta

import pandas as pd
import pytz
import yfinance as yf

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

# interval -> (yfinance interval, period to fetch, bar length)
FETCH_PLAN = {
    "5m": ("5m", "5d", timedelta(minutes=5)),
    "15m": ("15m", "30d", timedelta(minutes=15)),
    "1h": ("1h", "300d", timedelta(hours=1)),
    "4h": ("1h", "300d", timedelta(hours=4)),   # resampled from 1h
}

SESSION_OPEN = dtime(9, 30)
SESSION_CLOSE = dtime(16, 0)


def now_et() -> datetime:
    return datetime.now(ET)


def market_open(cfg: dict) -> bool:
    n = now_et()
    if n.weekday() > 4:
        return False
    return SESSION_OPEN <= n.time() < SESSION_CLOSE


def _clean(df: pd.DataFrame, bar_len: timedelta) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["close"])
    if df.empty:
        return df
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET)
    # regular session only
    t = df.index.time
    df = df[(t >= SESSION_OPEN) & (t < SESSION_CLOSE)]
    # drop the still-forming last bar
    if len(df) and df.index[-1] + bar_len > now_et():
        df = df.iloc[:-1]
    return df


def _resample_4h(df1h: pd.DataFrame) -> pd.DataFrame:
    """Session-anchored 4h bars: 09:30-13:30 and 13:30-16:00 (partial)."""
    if df1h.empty:
        return df1h
    out = []
    for day, day_df in df1h.groupby(df1h.index.date):
        r = day_df.resample("240min", origin=day_df.index[0]).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["close"])
        out.append(r)
    df4 = pd.concat(out)
    # last 4h bucket is complete once 4h elapsed OR the session has closed
    if len(df4):
        last_start = df4.index[-1]
        session_close = last_start.replace(hour=16, minute=0)
        if now_et() < min(last_start + timedelta(hours=4), session_close):
            df4 = df4.iloc[:-1]
    return df4


def fetch_bars(symbols: list, interval: str) -> dict:
    """Return {symbol: DataFrame} for one interval, batched in a single request."""
    yf_iv, period, bar_len = FETCH_PLAN[interval]
    raw = yf.download(
        tickers=symbols, interval=yf_iv, period=period,
        group_by="ticker", auto_adjust=True, prepost=False,
        threads=True, progress=False,
    )
    frames = {}
    for sym in symbols:
        try:
            df = raw[sym] if len(symbols) > 1 else raw
        except KeyError:
            continue
        df = _clean(df.copy(), FETCH_PLAN["1h"][2] if interval == "4h" else bar_len)
        if interval == "4h":
            df = _resample_4h(df)
        if len(df) >= 30:
            frames[sym] = df
    logger.info("interval %s: %d/%d symbols with data", interval, len(frames), len(symbols))
    return frames
