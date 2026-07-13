"""
VWAP band mean-reversion.

VWAP is the institutional benchmark price; extensions beyond ~2 standard
deviations of the session's price-VWAP spread tend to snap back intraday
(the well-documented intraday reversal effect). Entry is the RE-ENTRY bar —
price pokes outside the band and closes back inside it — not the extension
itself, so the alert is the turn, not the chase. Target is VWAP itself.
"""
import indicators as ta
from strategies.base import make_signal, risk_ok

NAME = "vwap_reversion"


def scan_at(symbol, df, interval, params, cfg, i=-1):
    if len(df) < 30:
        return None
    bar = df.iloc[i]
    bar_time = df.index[i]
    day = bar_time.date()

    day_upto = df[(df.index.date == day) & (df.index <= bar_time)]
    bars_per_min = {"5m": 5, "15m": 15}[interval]
    if len(day_upto) < max(params["min_bars"], params["skip_first_minutes"] // bars_per_min + 1):
        return None

    upto = df[df.index <= bar_time]
    vwap = ta.session_vwap(upto)
    sigma = ta.vwap_band_sigma(upto, vwap)
    v, s = vwap.iloc[-1], sigma.iloc[-1]
    if not s or s != s or s <= 0:
        return None

    lower = v - params["band_sigma"] * s
    upper = v + params["band_sigma"] * s
    atr = ta.atr(upto, cfg["risk"]["atr_period"]).iloc[-1]
    if not atr or atr != atr:
        return None

    direction = None
    # re-entry long: bar traded below the lower band but closed back inside
    if bar["low"] <= lower and bar["close"] > lower and bar["close"] < v:
        direction = "long"
        entry = bar["close"]
        stop = entry - params["stop_atr"] * atr
        target = v
    # re-entry short: bar traded above the upper band but closed back inside
    elif bar["high"] >= upper and bar["close"] < upper and bar["close"] > v:
        direction = "short"
        entry = bar["close"]
        stop = entry + params["stop_atr"] * atr
        target = v
    if direction is None:
        return None

    # target must be worth the risk (at least ~0.5R to VWAP)
    if abs(target - entry) < 0.5 * abs(entry - stop):
        return None
    if not risk_ok(entry, stop, cfg["risk"]["min_risk_pct"]):
        return None

    return make_signal(NAME, symbol, interval, direction, entry, stop, target, bar_time,
                       f"Re-entry after {params['band_sigma']:.0f}σ VWAP extension "
                       f"(VWAP {v:.2f} target)",
                       eod_exit=True)


def scan(symbol, df, interval, params, cfg):
    return scan_at(symbol, df, interval, params, cfg, i=-1)
