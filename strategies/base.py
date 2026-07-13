"""
Shared strategy contract.

Every strategy implements  scan(symbol, df, interval, params, cfg) -> dict|None
and must only signal when the trigger occurs ON THE LATEST COMPLETED BAR —
that is the fix for "alerts arriving after the entry point". A signal carries
its entry, protective stop and target so the trade plan is complete at alert
time. `scan_at` lets the replay engine evaluate any historical bar with the
exact same code path (no lookahead: each scan sees only data up to its bar).
"""


def make_signal(strategy, symbol, interval, direction, entry, stop, target,
                bar_time, reason, time_stop_bars=None, eod_exit=False):
    risk = abs(entry - stop)
    return {
        "strategy": strategy,
        "symbol": symbol,
        "interval": interval,
        "direction": direction,           # "long" | "short"
        "entry": round(float(entry), 4),
        "stop": round(float(stop), 4),
        "target": round(float(target), 4),
        "risk": round(float(risk), 4),
        "bar_time": bar_time.isoformat(),
        "reason": reason,
        "time_stop_bars": time_stop_bars,  # close after N bars if neither hit
        "eod_exit": eod_exit,              # intraday: flat by session close
    }


def risk_ok(entry, stop, min_risk_pct):
    """Reject degenerate signals whose stop is basically at the entry."""
    return abs(entry - stop) >= entry * (min_risk_pct / 100.0)
