"""
Opening Range Breakout (ORB).

The high/low of the first 15 minutes defines the range; the FIRST bar that
closes beyond it (with volume confirmation) is the entry trigger. One of the
best-documented intraday setups (Crabel 1990; Zarattini & Aziz 2023 showed a
5-minute ORB on liquid ETFs remained profitable 2016-2023).

Anti-chase guard: if the trigger close is already > max_chase_atr ATRs beyond
the level, the move is gone — skip rather than alert late.
"""
from datetime import time as dtime

import indicators as ta
from strategies.base import make_signal, risk_ok

NAME = "orb"


def scan_at(symbol, df, interval, params, cfg, i=-1):
    if len(df) < 30:
        return None
    bar = df.iloc[i]
    bar_time = df.index[i]
    day = bar_time.date()

    last_entry = dtime(*map(int, params["last_entry_et"].split(":")))
    if bar_time.time() > last_entry:
        return None

    day_df = df[df.index.date == day]
    # position of this bar within the session
    day_upto = day_df[day_df.index <= bar_time]
    bars_per_or = max(1, params["opening_range_minutes"] // {"5m": 5, "15m": 15}[interval])
    if len(day_upto) <= bars_per_or:
        return None  # still inside the opening range window

    or_bars = day_df.iloc[:bars_per_or]
    or_high, or_low = or_bars["high"].max(), or_bars["low"].min()

    # this must be the FIRST close beyond the range today
    prior = day_upto.iloc[bars_per_or:-1]
    if len(prior) and ((prior["close"] > or_high).any() or (prior["close"] < or_low).any()):
        return None

    atr = ta.atr(df, cfg["risk"]["atr_period"]).iloc[i]
    if not atr or atr != atr:
        return None

    # volume confirmation vs prior 10 bars
    upto = df[df.index <= bar_time]
    vol_avg = upto["volume"].iloc[-11:-1].mean()
    vol_ok = vol_avg > 0 and bar["volume"] >= params["volume_confirm_mult"] * vol_avg

    direction = None
    if bar["close"] > or_high:
        direction, level, stop_ref = "long", or_high, or_low
    elif bar["close"] < or_low:
        direction, level, stop_ref = "short", or_low, or_high
    if direction is None or not vol_ok:
        return None

    # anti-chase: trigger close must be near the breakout level
    if abs(bar["close"] - level) > params["max_chase_atr"] * atr:
        return None

    entry = bar["close"]
    if direction == "long":
        stop = max(stop_ref, entry - 2 * atr)   # cap risk on wide ranges
        target = entry + params["reward_r"] * (entry - stop)
    else:
        stop = min(stop_ref, entry + 2 * atr)
        target = entry - params["reward_r"] * (stop - entry)

    if not risk_ok(entry, stop, cfg["risk"]["min_risk_pct"]):
        return None

    return make_signal(NAME, symbol, interval, direction, entry, stop, target, bar_time,
                       f"First {params['opening_range_minutes']}min range break "
                       f"({'above' if direction == 'long' else 'below'} {level:.2f}) on "
                       f"{bar['volume'] / vol_avg:.1f}x volume",
                       eod_exit=True)


def scan(symbol, df, interval, params, cfg):
    return scan_at(symbol, df, interval, params, cfg, i=-1)
