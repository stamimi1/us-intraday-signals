"""
EMA 9/21 cross with 200-EMA trend filter.

Trend-following is the most robust systematic edge in the academic record
(Brock/Lakonishok/LeBaron 1992 on MA rules; Moskowitz/Ooi/Pedersen 2012 on
time-series momentum). The 200-EMA filter keeps entries on the side of the
higher-timeframe trend, which is where MA crosses historically earn their keep.
Signal fires only on the actual cross bar.
"""
import indicators as ta
from strategies.base import make_signal, risk_ok

NAME = "ema_cross"


def scan_at(symbol, df, interval, params, cfg, i=-1):
    if len(df) < params["trend"] + 10:
        return None
    upto = df.iloc[: len(df) + i + 1] if i < 0 else df.iloc[: i + 1]
    bar = upto.iloc[-1]
    bar_time = upto.index[-1]

    fast = ta.ema(upto["close"], params["fast"])
    slow = ta.ema(upto["close"], params["slow"])
    trend = ta.ema(upto["close"], params["trend"])
    atr = ta.atr(upto, cfg["risk"]["atr_period"]).iloc[-1]
    if not atr or atr != atr:
        return None

    f_now, f_prev = fast.iloc[-1], fast.iloc[-2]
    s_now, s_prev = slow.iloc[-1], slow.iloc[-2]
    t_now = trend.iloc[-1]

    direction = None
    if f_prev <= s_prev and f_now > s_now and bar["close"] > t_now:
        direction = "long"
    elif f_prev >= s_prev and f_now < s_now and bar["close"] < t_now:
        direction = "short"
    if direction is None:
        return None

    entry = bar["close"]
    lb = params["swing_lookback"]
    if direction == "long":
        swing = upto["low"].iloc[-lb:].min()
        stop = max(swing, entry - params["stop_atr_cap"] * atr)
        stop = min(stop, entry - params["stop_atr_floor"] * atr)
        target = entry + params["reward_r"] * (entry - stop)
    else:
        swing = upto["high"].iloc[-lb:].max()
        stop = min(swing, entry + params["stop_atr_cap"] * atr)
        stop = max(stop, entry + params["stop_atr_floor"] * atr)
        target = entry - params["reward_r"] * (stop - entry)

    if not risk_ok(entry, stop, cfg["risk"]["min_risk_pct"]):
        return None

    return make_signal(NAME, symbol, interval, direction, entry, stop, target, bar_time,
                       f"EMA{params['fast']}/{params['slow']} {'bullish' if direction == 'long' else 'bearish'} "
                       f"cross, price {'above' if direction == 'long' else 'below'} EMA{params['trend']}",
                       time_stop_bars=params["time_stop_bars"])


def scan(symbol, df, interval, params, cfg):
    return scan_at(symbol, df, interval, params, cfg, i=-1)
