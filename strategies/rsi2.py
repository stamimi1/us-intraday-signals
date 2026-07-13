"""
RSI(2) pullback (Larry Connors).

Buy a brief, sharp dip inside an established uptrend: RSI(2) under 10 while
price holds above its 200-period MA (mirror for shorts). Connors & Alvarez
published extensive multi-decade backtests of this on liquid US equities/ETFs
("Short Term Trading Strategies That Work") — one of the few retail-known
setups with a genuinely documented statistical record. Adapted here to 1h/4h
bars with an added ATR stop (Connors traded it stopless; a stop is non-
negotiable for automated forward-testing).
"""
import indicators as ta
from strategies.base import make_signal, risk_ok

NAME = "rsi2"


def scan_at(symbol, df, interval, params, cfg, i=-1):
    if len(df) < params["trend_ma"] + 10:
        return None
    upto = df.iloc[: len(df) + i + 1] if i < 0 else df.iloc[: i + 1]
    bar = upto.iloc[-1]
    bar_time = upto.index[-1]

    r = ta.rsi(upto["close"], params["rsi_period"])
    ma = ta.sma(upto["close"], params["trend_ma"]).iloc[-1]
    atr = ta.atr(upto, cfg["risk"]["atr_period"]).iloc[-1]
    if ma != ma or not atr or atr != atr:
        return None

    r_now, r_prev = r.iloc[-1], r.iloc[-2]
    direction = None
    # fire on the bar RSI2 first drops below/above the threshold (not while it sits there)
    if r_now < params["long_below"] <= r_prev and bar["close"] > ma:
        direction = "long"
        entry = bar["close"]
        stop = entry - params["stop_atr"] * atr
        target = entry + params["target_atr"] * atr
    elif r_now > params["short_above"] >= r_prev and bar["close"] < ma:
        direction = "short"
        entry = bar["close"]
        stop = entry + params["stop_atr"] * atr
        target = entry - params["target_atr"] * atr
    if direction is None:
        return None

    if not risk_ok(entry, stop, cfg["risk"]["min_risk_pct"]):
        return None

    return make_signal(NAME, symbol, interval, direction, entry, stop, target, bar_time,
                       f"RSI(2)={r_now:.0f} pullback {'in uptrend (>MA200)' if direction == 'long' else 'in downtrend (<MA200)'}",
                       time_stop_bars=params["time_stop_bars"])


def scan(symbol, df, interval, params, cfg):
    return scan_at(symbol, df, interval, params, cfg, i=-1)
