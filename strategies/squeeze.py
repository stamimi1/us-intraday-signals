"""
Volatility squeeze release (Bollinger inside Keltner, "TTM squeeze" family).

Volatility clusters: unusually tight ranges precede expansions (Crabel's
contraction principle; popularized as the TTM Squeeze). When the Bollinger
Bands have been squeezed inside the Keltner Channel for several bars and then
release, enter in the direction of momentum. Fires only on the release bar.
"""
import indicators as ta
from strategies.base import make_signal, risk_ok

NAME = "squeeze"


def scan_at(symbol, df, interval, params, cfg, i=-1):
    if len(df) < 60:
        return None
    upto = df.iloc[: len(df) + i + 1] if i < 0 else df.iloc[: i + 1]
    bar = upto.iloc[-1]
    bar_time = upto.index[-1]

    _, bb_up, bb_lo = ta.bollinger(upto["close"], params["bb_window"], params["bb_std"])
    _, kc_up, kc_lo = ta.keltner(upto, params["kc_window"], params["kc_mult"])
    atr = ta.atr(upto, cfg["risk"]["atr_period"]).iloc[-1]
    if not atr or atr != atr:
        return None

    squeezed = (bb_up < kc_up) & (bb_lo > kc_lo)
    if len(squeezed) < params["min_squeeze_bars"] + 2:
        return None

    # release bar: squeeze was on for >= N bars, now off
    was_on = squeezed.iloc[-(params["min_squeeze_bars"] + 1):-1].all()
    now_off = not squeezed.iloc[-1]
    if not (was_on and now_off):
        return None

    # momentum direction: close vs its mean over the momentum window
    mom = bar["close"] - upto["close"].iloc[-params["momentum_window"]:].mean()
    direction = "long" if mom > 0 else "short"

    entry = bar["close"]
    if direction == "long":
        stop = entry - params["stop_atr"] * atr
        target = entry + params["reward_r"] * (entry - stop)
    else:
        stop = entry + params["stop_atr"] * atr
        target = entry - params["reward_r"] * (stop - entry)

    if not risk_ok(entry, stop, cfg["risk"]["min_risk_pct"]):
        return None

    return make_signal(NAME, symbol, interval, direction, entry, stop, target, bar_time,
                       f"Squeeze release after {params['min_squeeze_bars']}+ compressed bars, "
                       f"momentum {'up' if direction == 'long' else 'down'}",
                       time_stop_bars=params["time_stop_bars"])


def scan(symbol, df, interval, params, cfg):
    return scan_at(symbol, df, interval, params, cfg, i=-1)
